"""Execution simulator, portfolio management, and trade policy package (Layer 6).

Governed by:
- docs/trade-policy-contract-v1.md
- ARCHITECTURE.md §1, §3 (Execution Simulator & Ledger)
- Layer 6 Gate: Event-driven execution, causal fills, and portfolio accounting.
"""

from __future__ import annotations

from .fee_schedule import (
    FEE_SCHEDULE_V1,
    BaseFeeSchedule,
    NSEEquityIntradayFeeSchedule,
    round_paisa,
)
from .models import (
    AmbiguityTreatment,
    ExecutionOrder,
    FillEvent,
    OrderRejectionReason,
    PortfolioState,
    PositionState,
    SimulatedTradeResult,
)
from .policy import TradePolicyEngine
from .portfolio import PortfolioManager
from .simulator import ExecutionSimulator

__all__ = [
    "AmbiguityTreatment",
    "BaseFeeSchedule",
    "ExecutionOrder",
    "ExecutionSimulator",
    "FEE_SCHEDULE_V1",
    "FillEvent",
    "NSEEquityIntradayFeeSchedule",
    "OrderRejectionReason",
    "PortfolioManager",
    "PortfolioState",
    "PositionState",
    "SimulatedTradeResult",
    "TradePolicyEngine",
    "round_paisa",
]
