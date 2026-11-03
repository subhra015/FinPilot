"""No-Trade Cash Reference Strategy (Layer 7).

Governed by:
- PROJECT_SPEC.md §5 (Comparators: No-trade reference)
- DATA_AND_PERFORMANCE_POLICY.md §5, §7
- Layer 7 Gate: Confirms zero simulated entries, zero costs, zero drift, and ledger parity.
"""

from __future__ import annotations

from decimal import Decimal

from finpilot.data.models import MarketDataRecord
from finpilot.db.enums import DataMode
from finpilot.features.models import FeatureVector
from finpilot.schemas.candles import CandleBar
from finpilot.schemas.trade_policy import TradeProposal


class NoTradeCashReference:
    """Benchmark comparator that never takes a simulated entry.

    Establishes the experimental control that any net performance from
    alternative strategies is not simply an artifact of market drift,
    time-in-sample, or simulator mechanics.
    """

    STRATEGY_ID = "REF-NOTRADE-V1"

    def __init__(self) -> None:
        self.strategy_id = self.STRATEGY_ID

    def evaluate_candle(
        self,
        bar: CandleBar | MarketDataRecord,
        features: FeatureVector | None = None,
        current_equity: Decimal = Decimal("30000.00"),
        mode: DataMode = DataMode.SYNTHETIC_DEMO,
    ) -> TradeProposal | None:
        """Never emits a trade proposal, preserving all capital in cash."""
        return None
