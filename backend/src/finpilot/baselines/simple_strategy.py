"""Predeclared Simple Baseline Strategy (Layer 7).

Governed by:
- PROJECT_SPEC.md §5 (Predeclared simple strategy: exactly one simple, fixed, non-ML rule set)
- docs/trade-policy-contract-v1.md (TP-V1 parameters: 1.5% stop, 3.0% target, 6-bar max hold)
- DATA_AND_PERFORMANCE_POLICY.md §2, §5
- Layer 7 Gate: Frozen, transparent, non-ML benchmark evaluated under identical assumptions.
"""

from __future__ import annotations

import uuid
from datetime import time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from finpilot.data.models import MarketDataRecord
from finpilot.db.enums import DataMode, OrderSide
from finpilot.features.models import FeatureVector
from finpilot.schemas.candles import CandleBar
from finpilot.schemas.trade_policy import TradeProposal

IST = ZoneInfo("Asia/Kolkata")
SESSION_ENTRY_CUTOFF = time(15, 0)


class PredeclaredSimpleStrategy:
    """Predeclared, transparent, rule-based intraday trend-momentum benchmark (STRAT-SIMPLE-V1).

    Rules:
    1. Trend: 9-period SMA > 21-period SMA (sma_ratio_9_21 > 0.0)
    2. Value / Location: Price above session VWAP approximation (vwap_approx_distance > 0.0)
    3. Momentum: Positive 1-bar return (ret_1 > 0.0) and RSI 50 to 70 (50 < rsi_14 <= 70)
    4. Participation: Relative volume >= 1.0 (causal_rel_vol >= 1.0)
    5. Session Cutoff: Signal candle must complete strictly before 15:00 IST
    6. Warm-up: Feature vector must be fully warmed up (is_fully_warmed_up == True, >= 21 bars)
    """

    STRATEGY_ID = "STRAT-SIMPLE-V1"
    POLICY_VERSION = "TP-V1"
    STOP_LOSS_PCT = Decimal("0.015")  # 1.5% fixed stop
    TAKE_PROFIT_PCT = Decimal("0.030")  # 3.0% fixed target
    MAX_HOLDING_BARS = 6  # 30 minutes (6 x 5m)

    def __init__(
        self,
        risk_fraction: Decimal = Decimal("0.01"),  # 1% risk per trade
        max_exposure_pct: Decimal = Decimal("0.50"),  # Max 50% capital per position
    ) -> None:
        self.strategy_id = self.STRATEGY_ID
        self.risk_fraction = risk_fraction
        self.max_exposure_pct = max_exposure_pct

    def calculate_quantity(
        self,
        equity: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
    ) -> int:
        """Calculate integer share quantity based on 1% equity risk capped by exposure."""
        risk_per_share = entry_price - stop_loss
        if risk_per_share <= Decimal("0.00"):
            return 1

        max_risk_amount = equity * self.risk_fraction
        shares_by_risk = int(max_risk_amount / risk_per_share)

        max_notional = equity * self.max_exposure_pct
        shares_by_exposure = int(max_notional / entry_price)

        shares = min(shares_by_risk, shares_by_exposure)
        return max(1, shares)

    def evaluate_candle(
        self,
        bar: CandleBar | MarketDataRecord,
        features: FeatureVector | None,
        current_equity: Decimal = Decimal("30000.00"),
        mode: DataMode = DataMode.SYNTHETIC_DEMO,
    ) -> TradeProposal | None:
        """Evaluate entry conditions for a completed 5-minute candle.

        Returns TradeProposal if all criteria are met, otherwise None.
        """
        if features is None or not features.is_fully_warmed_up:
            return None

        # Session Cutoff Check: No entries at or after 15:00 IST
        candle_ist = bar.timestamp.astimezone(IST)
        if candle_ist.time() >= SESSION_ENTRY_CUTOFF:
            return None

        vals = features.features

        # 1. Trend: sma_ratio_9_21 > 0.0
        sma_ratio = vals.get("sma_ratio_9_21")
        if sma_ratio is None or sma_ratio <= 0.0:
            return None

        # 2. Location: vwap_approx_distance > 0.0
        vwap_dist = vals.get("vwap_approx_distance")
        if vwap_dist is None or vwap_dist <= 0.0:
            return None

        # 3. Momentum: ret_1 > 0.0 and 50.0 < rsi_14 <= 70.0
        ret_1 = vals.get("ret_1")
        if ret_1 is None or ret_1 <= 0.0:
            return None

        rsi = vals.get("rsi_14")
        if rsi is None or rsi <= 50.0 or rsi > 70.0:
            return None

        # 4. Participation: causal_rel_vol >= 1.0
        rel_vol = vals.get("causal_rel_vol")
        if rel_vol is None or rel_vol < 1.0:
            return None

        # All criteria satisfied: construct strictly causal TradeProposal under TP-V1
        entry_price = Decimal(str(bar.close))
        stop_loss = Decimal(str(round(entry_price * (Decimal("1.0") - self.STOP_LOSS_PCT), 4)))
        target_price = Decimal(str(round(entry_price * (Decimal("1.0") + self.TAKE_PROFIT_PCT), 4)))

        # Sizing: Whole integer shares under risk and capital limits
        quantity = self.calculate_quantity(current_equity, entry_price, stop_loss)

        inst_id = getattr(bar, "instrument_id", features.instrument_id)
        proposal_id = f"PROP-{bar.symbol}-{int(bar.timestamp.timestamp())}-{uuid.uuid4().hex[:6]}"

        return TradeProposal(
            proposal_id=proposal_id,
            policy_version=self.POLICY_VERSION,
            instrument_id=inst_id,
            symbol=bar.symbol,
            decision_timestamp=bar.timestamp,
            earliest_entry_timestamp=bar.timestamp + timedelta(minutes=5),
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
            quantity=quantity,
            side=OrderSide.BUY,
            mode=mode,
        )
