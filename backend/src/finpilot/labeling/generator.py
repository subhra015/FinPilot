"""Trade-policy-aware label generator (Layer 8).

Governed by:
- docs/trade-policy-contract-v1.md (TP-V1 Policy Contract)
- docs/execution-policy.md (Layer 6 Matching Engine & Statutory Costs)
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 8 Gate: Labeling under realistic execution, next-bar entry, stop/target resolution,
  statutory costs, and integer share sizing (Approach A).
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from finpilot.data.models import MarketDataRecord
from finpilot.db.enums import OrderSide
from finpilot.execution.fee_schedule import (
    BaseFeeSchedule,
    NSEEquityIntradayFeeSchedule,
    round_paisa,
)
from finpilot.features.models import FeatureVector
from finpilot.features.universe import PointInTimeUniverseManager
from finpilot.schemas.candles import CandleBar
from finpilot.schemas.common import normalize_to_utc

from .models import LabelingApproach, TradeOutcomeReason, TradePolicyLabel

IST = ZoneInfo("Asia/Kolkata")
SESSION_ENTRY_CUTOFF = time(15, 0)
SESSION_SQUARE_OFF_CUTOFF = time(15, 15)


class TradePolicyLabelGenerator:
    """Generates ground-truth labels based on executable trade policy (TP-V1) outcomes.

    Invariants:
    1. Executable Entry: Signal candle completion at t emits a proposal; executable entry
       occurs strictly at next-candle open (t + 5m) with modelled slippage.
    2. Trade Policy Mechanics: Positions evaluate stop loss, target, gap fills, collision
       ambiguity, and compulsory square-off at 15:15 IST.
    3. Approach A (Shared Sizing): Uses integer share sizing under fixed ₹30,000 scenario capital
       and applies complete NSE statutory and broker fees (STT, GST, stamp duty, turnover charges).
       Binary label is 1 ONLY if Net P&L > 0.00.
    4. Anti-Leakage: Uses point-in-time features derived strictly from candles <= t.
    """

    def __init__(
        self,
        fee_schedule: BaseFeeSchedule | None = None,
        stop_loss_pct: Decimal = Decimal("0.015"),  # 1.5% fixed stop
        take_profit_pct: Decimal = Decimal("0.030"),  # 3.0% fixed target
        max_holding_bars: int = 6,  # 30 minutes
        modelled_slippage_bps: Decimal = Decimal("2.0"),  # 2 basis points
        scenario_equity: Decimal = Decimal("30000.00"),  # ₹30,000 scenario
        risk_fraction: Decimal = Decimal("0.01"),  # 1% risk per trade = ₹300
        max_exposure_pct: Decimal = Decimal("0.50"),  # Max 50% capital per position
        labeling_approach: LabelingApproach = LabelingApproach.APPROACH_A_SHARED_SIZING,
    ) -> None:
        self.fee_schedule = fee_schedule or NSEEquityIntradayFeeSchedule()
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_holding_bars = max_holding_bars
        self.modelled_slippage_bps = modelled_slippage_bps
        self.scenario_equity = scenario_equity
        self.risk_fraction = risk_fraction
        self.max_exposure_pct = max_exposure_pct
        self.labeling_approach = labeling_approach

    def calculate_quantity(
        self,
        entry_price: Decimal,
        stop_loss: Decimal,
    ) -> int:
        """Calculate integer share quantity based on risk fraction and exposure cap."""
        risk_per_share = entry_price - stop_loss
        if risk_per_share <= Decimal("0.00"):
            return 1

        max_risk_amount = self.scenario_equity * self.risk_fraction
        shares_by_risk = int(max_risk_amount / risk_per_share)

        max_notional = self.scenario_equity * self.max_exposure_pct
        shares_by_exposure = int(max_notional / entry_price)

        return max(1, min(shares_by_risk, shares_by_exposure))

    def generate_labels_for_series(
        self,
        instrument_id: int,
        symbol: str,
        bars: list[CandleBar | MarketDataRecord],
        features_by_time: dict[datetime, FeatureVector],
        pit_universe_manager: PointInTimeUniverseManager | None = None,
    ) -> tuple[list[TradePolicyLabel], int]:
        """Generate labeled samples for a chronological series of bars for one instrument.

        Returns:
            tuple[list[TradePolicyLabel], int]: (labeled_samples, excluded_rows_count)
        """
        if not bars:
            return [], 0

        # Sort bars strictly chronologically
        sorted_bars = sorted(bars, key=lambda b: normalize_to_utc(b.timestamp))
        labels: list[TradePolicyLabel] = []
        excluded_count = 0

        total_bars = len(sorted_bars)
        for i in range(total_bars):
            dec_bar = sorted_bars[i]
            dec_time_utc = normalize_to_utc(dec_bar.timestamp)
            dec_time_ist = dec_time_utc.astimezone(IST)

            # 1. Session Cutoff: No proposals at or after 15:00 IST
            if dec_time_ist.time() >= SESSION_ENTRY_CUTOFF:
                excluded_count += 1
                continue

            # 2. Warmup & Feature Availability
            feat = features_by_time.get(dec_time_utc)
            if feat is None or not feat.is_fully_warmed_up:
                excluded_count += 1
                continue

            # 3. Point-in-time Universe Eligibility
            is_pit_eligible = True
            if pit_universe_manager is not None:
                snapshot = pit_universe_manager.get_point_in_time_universe(dec_time_utc)
                eligible_symbols = {m.symbol for m in snapshot.members if m.is_eligible}
                if symbol not in eligible_symbols:
                    is_pit_eligible = False
                    excluded_count += 1
                    continue

            # 4. Check for Executable Entry Bar (strictly next candle i + 1)
            if i + 1 >= total_bars:
                # No subsequent bar available in dataset to execute entry
                excluded_count += 1
                continue

            entry_bar = sorted_bars[i + 1]
            entry_time_utc = normalize_to_utc(entry_bar.timestamp)
            entry_time_ist = entry_time_utc.astimezone(IST)

            # Must be in the same trading session (no carrying entry proposals overnight)
            if entry_time_ist.date() != dec_time_ist.date():
                excluded_count += 1
                continue

            # Volume Check: Zero volume on entry bar prevents fill
            if entry_bar.volume <= 0:
                excluded_count += 1
                continue

            # 5. Execute Entry at Next-Bar Open with Slippage
            slip_multiplier = Decimal("1.0") + (self.modelled_slippage_bps / Decimal("10000.0"))
            entry_open = Decimal(str(entry_bar.open))
            entry_fill_price = round_paisa(entry_open * slip_multiplier)

            stop_loss = round_paisa(entry_fill_price * (Decimal("1.0") - self.stop_loss_pct))
            take_profit = round_paisa(entry_fill_price * (Decimal("1.0") + self.take_profit_pct))

            if self.labeling_approach == LabelingApproach.APPROACH_A_SHARED_SIZING:
                quantity = self.calculate_quantity(entry_fill_price, stop_loss)
            else:
                quantity = 1

            # 6. Forward-Evaluate Position Lifecycle through Subsequent Bars
            exit_bar: CandleBar | MarketDataRecord | None = None
            exit_fill_price = Decimal("0.00")
            outcome_reason = TradeOutcomeReason.SESSION_SQUARE_OFF
            is_ambiguous_exit = False
            is_gap_fill = False
            holding_bars = 0

            # Scan from entry bar forward
            for j in range(i + 1, total_bars):
                curr_bar = sorted_bars[j]
                curr_time_utc = normalize_to_utc(curr_bar.timestamp)
                curr_time_ist = curr_time_utc.astimezone(IST)

                # If session changed without prior exit, square off at previous bar close
                if curr_time_ist.date() != dec_time_ist.date():
                    break

                holding_bars = j - (i + 1) + 1
                bar_open = Decimal(str(curr_bar.open))
                bar_high = Decimal(str(curr_bar.high))
                bar_low = Decimal(str(curr_bar.low))

                # Check Mandatory Session Cutoff (15:15 IST)
                if curr_time_ist.time() >= SESSION_SQUARE_OFF_CUTOFF:
                    exit_slip = Decimal("1.0") - (self.modelled_slippage_bps / Decimal("10000.0"))
                    exit_fill_price = round_paisa(bar_open * exit_slip)
                    outcome_reason = TradeOutcomeReason.SESSION_SQUARE_OFF
                    exit_bar = curr_bar
                    break

                # Check Max Holding Period Expiry
                if holding_bars >= self.max_holding_bars:
                    exit_slip = Decimal("1.0") - (self.modelled_slippage_bps / Decimal("10000.0"))
                    exit_fill_price = round_paisa(bar_open * exit_slip)
                    outcome_reason = TradeOutcomeReason.MAX_HOLDING_EXPIRY
                    exit_bar = curr_bar
                    break

                # Price Bounds Check
                stop_breached = bar_low <= stop_loss
                target_breached = bar_high >= take_profit

                if stop_breached and target_breached:
                    # Same-bar collision: conservative stop loss first
                    is_ambiguous_exit = True
                    is_gap = bar_open < stop_loss
                    if is_gap:
                        exit_fill_price = bar_open
                        is_gap_fill = True
                    else:
                        exit_fill_price = stop_loss
                    outcome_reason = TradeOutcomeReason.SAME_BAR_AMBIGUOUS_STOP
                    exit_bar = curr_bar
                    break
                elif stop_breached:
                    is_gap = bar_open < stop_loss
                    if is_gap:
                        exit_fill_price = bar_open
                        is_gap_fill = True
                        outcome_reason = TradeOutcomeReason.GAP_STOP_HIT
                    else:
                        exit_fill_price = stop_loss
                        outcome_reason = TradeOutcomeReason.STOP_LOSS_HIT
                    exit_bar = curr_bar
                    break
                elif target_breached:
                    exit_fill_price = bar_open if bar_open > take_profit else take_profit
                    outcome_reason = TradeOutcomeReason.TARGET_HIT
                    exit_bar = curr_bar
                    break

            # If no exit was triggered during loop (e.g. data stream ended abruptly)
            if exit_bar is None:
                last_eval_bar = sorted_bars[min(total_bars - 1, i + self.max_holding_bars)]
                exit_bar = last_eval_bar
                exit_fill_price = round_paisa(Decimal(str(last_eval_bar.close)))
                outcome_reason = TradeOutcomeReason.DATA_FEED_INTERRUPTED
                holding_bars = max(1, total_bars - 1 - i)

            exit_time_utc = normalize_to_utc(exit_bar.timestamp)

            # 7. Calculate Costs and P&L
            entry_notional = round_paisa(entry_fill_price * Decimal(quantity))
            exit_notional = round_paisa(exit_fill_price * Decimal(quantity))
            gross_pnl = round_paisa(exit_notional - entry_notional)

            if self.labeling_approach == LabelingApproach.APPROACH_A_SHARED_SIZING:
                entry_cost = self.fee_schedule.calculate_costs(
                    side=OrderSide.BUY,
                    price=entry_fill_price,
                    quantity=quantity,
                    modelled_slippage_bps=self.modelled_slippage_bps,
                )
                exit_cost = self.fee_schedule.calculate_costs(
                    side=OrderSide.SELL,
                    price=exit_fill_price,
                    quantity=quantity,
                    modelled_slippage_bps=self.modelled_slippage_bps,
                )
                total_fees = round_paisa(entry_cost.total_costs + exit_cost.total_costs)
                net_pnl = round_paisa(gross_pnl - total_fees)
            else:
                total_fees = Decimal("0.00")
                net_pnl = gross_pnl

            gross_return = (
                (gross_pnl / entry_notional).quantize(Decimal("0.0001"))
                if entry_notional > Decimal("0.00")
                else Decimal("0.00")
            )
            net_return = (
                (net_pnl / entry_notional).quantize(Decimal("0.0001"))
                if entry_notional > Decimal("0.00")
                else Decimal("0.00")
            )

            # Binary label: 1 ONLY if net_pnl > 0.00 under executable policy
            binary_label = 1 if net_pnl > Decimal("0.00") else 0

            # Filter out non-finite or None values in feature map for serialization
            clean_features: dict[str, float | None] = {
                k: v for k, v in feat.features.items() if v is not None
            }

            label = TradePolicyLabel(
                sample_id=f"LBL-{instrument_id}-{dec_time_utc.strftime('%Y%m%d%H%M')}",
                instrument_id=instrument_id,
                symbol=symbol,
                decision_time=dec_time_utc,
                entry_time=entry_time_utc,
                exit_time=exit_time_utc,
                holding_bars=holding_bars,
                entry_price=entry_fill_price,
                exit_price=exit_fill_price,
                quantity=quantity,
                gross_pnl=gross_pnl,
                fees=total_fees,
                net_pnl=net_pnl,
                gross_return=gross_return,
                net_return=net_return,
                binary_label=binary_label,
                outcome_reason=outcome_reason,
                is_ambiguous_exit=is_ambiguous_exit,
                is_gap_fill=is_gap_fill,
                pit_universe_eligible=is_pit_eligible,
                features=clean_features,
                policy_version="TP-V1",
                labeling_approach=self.labeling_approach,
            )
            labels.append(label)

        return labels, excluded_count
