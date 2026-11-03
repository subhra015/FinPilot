"""Core Independent Risk Evaluator implementing deny-by-default trade filtering (Layer 11).

Governed by:
- PROJECT_SPEC.md §4, §5, §7
- DATA_AND_PERFORMANCE_POLICY.md §2, §7
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-09, SEC-19
- Layer 11 Gate: Complete independent authority, 11 deny-by-default checks,
  explicit distinction between entries and exits, tamper-evident RiskAuthorization.
"""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from finpilot.data.models import MarketDataRecord
from finpilot.db.enums import OrderSide
from finpilot.execution.fee_schedule import (
    BaseFeeSchedule,
    NSEEquityIntradayFeeSchedule,
    round_paisa,
)
from finpilot.schemas.candles import CandleBar
from finpilot.schemas.trade_policy import TradeProposal

from .models import (
    PositionCloseIntent,
    RiskAuthorization,
    RiskConfig,
    RiskDecisionStatus,
    RiskEvaluationResult,
    RiskMetricsSnapshot,
    RiskRejectionReason,
)

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN_TIME = time(9, 15)
ENTRY_CUTOFF_TIME = time(15, 0)
FORCED_EXIT_TIME = time(15, 15)
MARKET_CLOSE_TIME = time(15, 30)


class RiskEvaluator:
    """Evaluates trade proposals and close intents against independent risk limits.

    Invariants:
    1. Independent Authority: ML models or trading strategies CANNOT authorize trades
       or bypass risk checks. RiskEvaluator is the sole authority for issuing RiskAuthorization.
    2. Deny-by-Default: Any violation immediately halts authorization and returns machine-readable
       rejection reasons.
    3. Entry vs. Exit Distinction: Closing positions is never blocked by entry cutoffs or cash,
       but close fills are never assumed if market data is missing or invalid.
    4. Deterministic Replay: Evaluating identical market and portfolio states produces identical
       risk decision outcomes.
    """

    def __init__(
        self,
        config: RiskConfig | None = None,
        fee_schedule: BaseFeeSchedule | None = None,
    ) -> None:
        self.config = config or RiskConfig()
        self.fee_schedule = fee_schedule or NSEEquityIntradayFeeSchedule()

    def evaluate_entry_proposal(
        self,
        proposal: TradeProposal,
        candle: CandleBar | MarketDataRecord | None,
        available_cash: Decimal,
        total_equity: Decimal,
        current_positions: list[dict[str, Any]] | None = None,
        active_order_proposal_ids: set[str] | None = None,
        daily_realized_loss: Decimal = Decimal("0.00"),
        current_drawdown_pct: float = 0.0,
        model_id: str = "MODEL-LOGREG-V1",
        current_timestamp: datetime | None = None,
    ) -> RiskEvaluationResult:
        """Evaluate a new long-only entry proposal against all 11 deny-by-default risk rules."""
        now_utc = current_timestamp or datetime.now(UTC)
        token_seed = f"{proposal.proposal_id}:{now_utc.isoformat()}".encode()
        suffix = hashlib.sha256(token_seed).hexdigest()[:12]
        decision_id = f"RSK-DEC-{suffix}"
        positions = current_positions or []
        open_pos_ids = active_order_proposal_ids or set()

        # Compute point-in-time metrics
        current_pos_count = len(positions)
        current_inst_exposure = sum(
            (
                Decimal(str(p.get("notional", "0.00")))
                for p in positions
                if p.get("symbol") == proposal.symbol
            ),
            Decimal("0.00"),
        )

        metrics = RiskMetricsSnapshot(
            available_cash=round_paisa(available_cash),
            total_equity=round_paisa(total_equity),
            current_position_count=current_pos_count,
            daily_realized_loss=round_paisa(daily_realized_loss),
            current_drawdown_pct=round(current_drawdown_pct, 4),
            current_instrument_exposure=round_paisa(current_inst_exposure),
        )

        rejection_reasons: list[RiskRejectionReason] = []
        rejection_details: list[str] = []

        # ------------------------------------------------------------------
        # Rule 1: Administrative Kill Switch & Manual Trading Pause
        # ------------------------------------------------------------------
        if self.config.kill_switch_active:
            rejection_reasons.append(RiskRejectionReason.KILL_SWITCH_ACTIVE)
            rejection_details.append("Emergency kill switch is actively engaged.")

        if self.config.manual_trading_paused:
            rejection_reasons.append(RiskRejectionReason.MANUAL_TRADING_PAUSED)
            rejection_details.append("Trading is currently paused by administrator.")

        # ------------------------------------------------------------------
        # Rule 2: Governance Allowlist & Trading Mode
        # ------------------------------------------------------------------
        if proposal.symbol not in self.config.approved_instruments:
            rejection_reasons.append(RiskRejectionReason.UNSUPPORTED_INSTRUMENT)
            rejection_details.append(
                f"Symbol '{proposal.symbol}' is not in approved instruments: "
                f"{self.config.approved_instruments}"
            )

        if proposal.policy_version != self.config.approved_policy_version:
            rejection_reasons.append(RiskRejectionReason.POLICY_VERSION_MISMATCH)
            rejection_details.append(
                f"Proposal policy '{proposal.policy_version}' does not match "
                f"approved '{self.config.approved_policy_version}'"
            )

        if model_id not in self.config.approved_model_ids:
            rejection_reasons.append(RiskRejectionReason.MODEL_VERSION_MISMATCH)
            rejection_details.append(
                f"Model ID '{model_id}' is not in approved models: "
                f"{self.config.approved_model_ids}"
            )

        # ------------------------------------------------------------------
        # Rule 3: Market Data Validity, Freshness & Session Geometry
        # ------------------------------------------------------------------
        if candle is None:
            rejection_reasons.append(RiskRejectionReason.DATA_STALE_OR_MISSING)
            rejection_details.append("Market candle data is missing for decision timestamp.")
        else:
            # Price validity
            c_open = Decimal(str(candle.open))
            c_high = Decimal(str(candle.high))
            c_low = Decimal(str(candle.low))
            c_close = Decimal(str(candle.close))

            if c_open <= 0 or c_high <= 0 or c_low <= 0 or c_close <= 0 or candle.volume < 0:
                rejection_reasons.append(RiskRejectionReason.MARKET_DATA_INVALID)
                rejection_details.append("Non-positive prices or negative volume in market candle.")

            if c_high < max(c_open, c_close, c_low) or c_low > min(c_open, c_close, c_high):
                rejection_reasons.append(RiskRejectionReason.MARKET_DATA_INVALID)
                rejection_details.append("OHLC geometry violation in market candle.")

            # Session timing (Asia/Kolkata)
            candle_ist = candle.timestamp.astimezone(IST)
            candle_time = candle_ist.time()

            if candle_time < MARKET_OPEN_TIME or candle_time > MARKET_CLOSE_TIME:
                rejection_reasons.append(RiskRejectionReason.OUT_OF_SESSION)
                rejection_details.append(
                    f"Candle time {candle_time} is outside NSE regular session "
                    f"({MARKET_OPEN_TIME} to {MARKET_CLOSE_TIME} IST)."
                )

            # Session entry cutoff: strictly no new entries after 15:00 IST
            if candle_time > ENTRY_CUTOFF_TIME:
                rejection_reasons.append(RiskRejectionReason.SESSION_ENTRY_CUTOFF)
                rejection_details.append(
                    f"Candle time {candle_time} exceeds 15:00 IST session entry cutoff."
                )

        # ------------------------------------------------------------------
        # Rule 4: Duplicate Orders & Unresolved Position State
        # ------------------------------------------------------------------
        if proposal.proposal_id in open_pos_ids:
            rejection_reasons.append(RiskRejectionReason.DUPLICATE_SIGNAL_OR_ORDER)
            rejection_details.append(
                f"Duplicate proposal ID '{proposal.proposal_id}' already has an active order."
            )

        existing_pos = next((p for p in positions if p.get("symbol") == proposal.symbol), None)
        if existing_pos is not None:
            rejection_reasons.append(RiskRejectionReason.UNRESOLVED_POSITION_STATE)
            rejection_details.append(
                f"Instrument '{proposal.symbol}' already has an open position (re-entry forbidden)."
            )

        # ------------------------------------------------------------------
        # Rule 5: Maximum Concurrent Positions Cap
        # ------------------------------------------------------------------
        if current_pos_count >= self.config.max_concurrent_positions:
            rejection_reasons.append(RiskRejectionReason.MAX_CONCURRENT_POSITIONS_EXCEEDED)
            rejection_details.append(
                f"Current positions ({current_pos_count}) reached maximum limit "
                f"({self.config.max_concurrent_positions})."
            )

        # ------------------------------------------------------------------
        # Rule 6: Circuit Breakers — Daily Loss & Drawdown Limits
        # ------------------------------------------------------------------
        is_circuit_broken = False
        is_suspended = False

        if daily_realized_loss >= self.config.max_daily_loss:
            rejection_reasons.append(RiskRejectionReason.DAILY_LOSS_LIMIT_EXCEEDED)
            rejection_details.append(
                f"Daily realized loss (₹{daily_realized_loss}) exceeded limit "
                f"(₹{self.config.max_daily_loss})."
            )
            is_circuit_broken = True

        if current_drawdown_pct >= self.config.max_drawdown_pct:
            rejection_reasons.append(RiskRejectionReason.DRAWDOWN_SUSPENSION_TRIGGERED)
            rejection_details.append(
                f"Current drawdown ({current_drawdown_pct*100:.1f}%) reached suspension threshold "
                f"({self.config.max_drawdown_pct*100:.1f}%)."
            )
            is_suspended = True

        # ------------------------------------------------------------------
        # Rule 7: Sizing, Cash Affordability & Adverse Execution Buffer
        # ------------------------------------------------------------------
        if proposal.quantity < 1:
            rejection_reasons.append(RiskRejectionReason.NON_POSITIVE_QUANTITY)
            rejection_details.append(f"Quantity must be at least 1, got {proposal.quantity}")

        # Sizing and adverse execution price limit
        slip_buffer = self.config.max_slippage_buffer_bps / Decimal("10000.0")
        max_adverse_entry_price = round_paisa(proposal.entry_price * (Decimal("1.0") + slip_buffer))
        estimated_notional = proposal.entry_price * Decimal(proposal.quantity)

        # Statutory fees on entry
        est_fees = self.fee_schedule.calculate_costs(
            side=OrderSide.BUY,
            price=max_adverse_entry_price,
            quantity=proposal.quantity,
        )
        total_required_capital = round_paisa(
            (max_adverse_entry_price * Decimal(proposal.quantity)) + est_fees.total_costs
        )

        if total_required_capital > available_cash:
            rejection_reasons.append(RiskRejectionReason.INSUFFICIENT_AVAILABLE_CASH)
            rejection_details.append(
                f"Required capital ₹{total_required_capital} exceeds cash ₹{available_cash}."
            )

        # ------------------------------------------------------------------
        # Rule 8: Planned Stop Risk Limit
        # ------------------------------------------------------------------
        has_invalid_price = (
            proposal.stop_loss >= proposal.entry_price
            or proposal.target_price <= proposal.entry_price
        )
        if has_invalid_price:
            rejection_reasons.append(RiskRejectionReason.INVALID_PRICE_RELATIONSHIP)
            rejection_details.append(
                f"Invalid long-only geometry: stop ({proposal.stop_loss}) >= "
                f"entry ({proposal.entry_price}) or target ({proposal.target_price}) <= entry."
            )
        else:
            per_share_risk = proposal.entry_price - proposal.stop_loss
            planned_stop_risk = round_paisa(
                per_share_risk * Decimal(proposal.quantity) + est_fees.total_costs
            )
            max_allowed_stop_risk = round_paisa(
                total_equity * self.config.max_planned_stop_risk_pct
            )

            if planned_stop_risk > max_allowed_stop_risk:
                rejection_reasons.append(RiskRejectionReason.EXCESSIVE_STOP_RISK)
                rejection_details.append(
                    f"Planned stop risk ₹{planned_stop_risk} exceeds limit "
                    f"₹{max_allowed_stop_risk} "
                    f"({self.config.max_planned_stop_risk_pct*100}% of equity)."
                )

        # ------------------------------------------------------------------
        # Rule 9: Exposure & Concentration Caps
        # ------------------------------------------------------------------
        max_pos_cap = round_paisa(total_equity * self.config.max_exposure_per_instrument_pct)
        if estimated_notional > max_pos_cap:
            rejection_reasons.append(RiskRejectionReason.POSITION_EXPOSURE_CAP_EXCEEDED)
            rejection_details.append(
                f"Position notional ₹{estimated_notional} exceeds cap ₹{max_pos_cap}."
            )

        current_total_exposure = sum(
            (Decimal(str(p.get("notional", "0.00"))) for p in positions),
            Decimal("0.00"),
        )
        total_exposure_after = current_total_exposure + estimated_notional
        max_tot_cap = round_paisa(total_equity * self.config.max_total_exposure_pct)

        if total_exposure_after > max_tot_cap:
            rejection_reasons.append(RiskRejectionReason.TOTAL_EXPOSURE_CAP_EXCEEDED)
            rejection_details.append(
                f"Total exposure ₹{total_exposure_after} exceeds total exposure cap ₹{max_tot_cap}."
            )

        # ------------------------------------------------------------------
        # Decision Synthesis & Authorization Generation
        # ------------------------------------------------------------------
        if rejection_reasons:
            if is_circuit_broken:
                status = RiskDecisionStatus.CIRCUIT_BROKEN
            elif is_suspended:
                status = RiskDecisionStatus.SUSPENDED
            else:
                status = RiskDecisionStatus.REJECTED

            return RiskEvaluationResult(
                decision_id=decision_id,
                status=status,
                authorization=None,
                rejection_reasons=rejection_reasons,
                rejection_details=rejection_details,
                metrics_snapshot=metrics,
                evaluated_at=now_utc,
            )

        # All checks passed: issue cryptographically sealed RiskAuthorization
        auth_id = f"AUTH-RISK-{suffix}"
        auth = RiskAuthorization.create(
            authorization_id=auth_id,
            proposal_id=proposal.proposal_id,
            model_id=model_id,
            symbol=proposal.symbol,
            instrument_id=proposal.instrument_id,
            authorized_quantity=proposal.quantity,
            allocated_capital=total_required_capital,
            max_adverse_entry_price=max_adverse_entry_price,
            stop_loss_limit=proposal.stop_loss,
            target_price_limit=proposal.target_price,
            authorized_at=now_utc,
            expires_at=proposal.earliest_entry_timestamp,
            policy_version=self.config.approved_policy_version,
            side=proposal.side,
        )

        return RiskEvaluationResult(
            decision_id=decision_id,
            status=RiskDecisionStatus.AUTHORIZED,
            authorization=auth,
            rejection_reasons=[],
            rejection_details=[],
            metrics_snapshot=metrics,
            evaluated_at=now_utc,
        )

    def evaluate_close_intent(
        self,
        close_intent: PositionCloseIntent,
        candle: CandleBar | MarketDataRecord | None,
        current_timestamp: datetime | None = None,
    ) -> RiskEvaluationResult:
        """Evaluate intent to close an open position (Exit).

        Crucial Rule: Closing positions is NEVER blocked by entry cutoffs, cash limits,
        or concurrent position caps. However, a close is NEVER assumed to fill if market
        data is missing, invalid, or bar volume is zero.
        """
        now_utc = current_timestamp or datetime.now(UTC)
        token_seed = f"{close_intent.close_id}:{now_utc.isoformat()}".encode()
        suffix = hashlib.sha256(token_seed).hexdigest()[:12]
        decision_id = f"RSK-EXIT-{suffix}"

        metrics = RiskMetricsSnapshot(
            available_cash=Decimal("0.00"),
            total_equity=Decimal("0.00"),
            current_position_count=1,
            daily_realized_loss=Decimal("0.00"),
            current_drawdown_pct=0.0,
            current_instrument_exposure=Decimal("0.00"),
        )

        rejection_reasons: list[RiskRejectionReason] = []
        rejection_details: list[str] = []

        # Market data must be available to close
        if candle is None:
            rejection_reasons.append(RiskRejectionReason.DATA_STALE_OR_MISSING)
            rejection_details.append(
                f"Cannot close position for {close_intent.symbol}: market candle is missing."
            )
        else:
            if candle.volume <= 0:
                rejection_reasons.append(RiskRejectionReason.MARKET_DATA_INVALID)
                rejection_details.append(
                    f"Cannot close position for {close_intent.symbol}: zero volume in market bar."
                )

            close_p = Decimal(str(candle.close))
            if close_p <= 0 or math.isnan(candle.close) or math.isinf(candle.close):
                rejection_reasons.append(RiskRejectionReason.MARKET_DATA_INVALID)
                rejection_details.append(
                    f"Cannot close position for {close_intent.symbol}: "
                    f"invalid close price {candle.close}."
                )

        if rejection_reasons:
            return RiskEvaluationResult(
                decision_id=decision_id,
                status=RiskDecisionStatus.REJECTED,
                authorization=None,
                rejection_reasons=rejection_reasons,
                rejection_details=rejection_details,
                metrics_snapshot=metrics,
                evaluated_at=now_utc,
            )

        # Authorized for immediate exit fill
        auth_id = f"AUTH-CLOSE-{suffix}"
        auth = RiskAuthorization.create(
            authorization_id=auth_id,
            proposal_id=close_intent.close_id,
            model_id="RISK-FORCED-EXIT",
            symbol=close_intent.symbol,
            instrument_id=close_intent.instrument_id,
            authorized_quantity=close_intent.quantity_to_close,
            allocated_capital=Decimal("0.01"),  # Exits release capital
            max_adverse_entry_price=Decimal("1000000.00"),
            stop_loss_limit=Decimal("0.01"),
            target_price_limit=Decimal("1000000.00"),
            authorized_at=now_utc,
            expires_at=close_intent.timestamp,
            policy_version=self.config.approved_policy_version,
            side=OrderSide.SELL,
        )

        return RiskEvaluationResult(
            decision_id=decision_id,
            status=RiskDecisionStatus.AUTHORIZED,
            authorization=auth,
            rejection_reasons=[],
            rejection_details=[],
            metrics_snapshot=metrics,
            evaluated_at=now_utc,
        )
