"""Domain models for execution, fills, positions, and portfolio state (Layer 6).

Governed by:
- docs/trade-policy-contract-v1.md
- ARCHITECTURE.md §1, §3
- Layer 6 Gate: Event-driven simulator, causal fill timing, and accounting integrity.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from finpilot.db.enums import DataMode, OrderSide, OrderStatus, OrderType
from finpilot.schemas.common import normalize_to_utc
from finpilot.schemas.errors import DomainValidationError, ErrorCode
from finpilot.schemas.execution_cost import CostBreakdown


class AmbiguityTreatment(StrEnum):
    """Handling strategy for same-bar stop and target breaches."""

    CONSERVATIVE_STOP_FIRST = "CONSERVATIVE_STOP_FIRST"
    OPTIMISTIC_TARGET_FIRST = "OPTIMISTIC_TARGET_FIRST"
    NONE = "NONE"


class OrderRejectionReason(StrEnum):
    """Standardized reasons for rejecting a simulated trade opportunity."""

    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    EXCEEDS_EXPOSURE_CAP = "EXCEEDS_EXPOSURE_CAP"
    OUTSIDE_SESSION_HOURS = "OUTSIDE_SESSION_HOURS"
    DUPLICATE_ORDER_ID = "DUPLICATE_ORDER_ID"
    INVALID_PRICE_RELATIONSHIP = "INVALID_PRICE_RELATIONSHIP"
    UNAUTHORIZED = "UNAUTHORIZED"
    ZERO_QUANTITY = "ZERO_QUANTITY"
    MARKET_HALTED = "MARKET_HALTED"


class ExecutionOrder(BaseModel):
    """An executable order tracked by the simulator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(..., min_length=1, max_length=64)
    proposal_id: str = Field(..., min_length=1, max_length=64)
    portfolio_id: int = Field(..., ge=1)
    instrument_id: int = Field(..., ge=1)
    symbol: str = Field(..., min_length=1, max_length=20)
    order_type: OrderType = Field(default=OrderType.MARKET)
    side: OrderSide = Field(default=OrderSide.BUY)
    quantity: int = Field(..., ge=1, le=1000000, description="Integer share quantity only")
    filled_quantity: int = Field(default=0, ge=0)
    price: Decimal | None = Field(default=None, gt=Decimal("0"))
    status: OrderStatus = Field(default=OrderStatus.PENDING)
    created_at: datetime
    signal_timestamp: datetime = Field(
        ..., description="Timestamp of completed candle that produced signal"
    )
    earliest_entry_timestamp: datetime = Field(
        ..., description="Earliest allowable execution time (strictly > signal_timestamp)"
    )
    expiry_timestamp: datetime = Field(
        ..., description="Timestamp after which unfilled order expires"
    )
    stop_loss: Decimal | None = Field(default=None, gt=Decimal("0"))
    target_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    risk_authorization_id: str | None = Field(default=None, max_length=100)
    mode: DataMode = Field(default=DataMode.HISTORICAL_REPLAY)

    @field_validator(
        "created_at",
        "signal_timestamp",
        "earliest_entry_timestamp",
        "expiry_timestamp",
        mode="before",
    )
    @classmethod
    def normalize_timestamps(cls, v: Any) -> datetime:
        return normalize_to_utc(v)

    @model_validator(mode="after")
    def validate_causal_timing_and_fill(self) -> ExecutionOrder:
        if self.earliest_entry_timestamp <= self.signal_timestamp:
            raise DomainValidationError(
                f"Causal timing violation: earliest_entry_timestamp "
                f"({self.earliest_entry_timestamp.isoformat()}) must be strictly after "
                f"signal_timestamp ({self.signal_timestamp.isoformat()}).",
                field="earliest_entry_timestamp",
                code=ErrorCode.VALIDATION_ERROR,
            )
        if self.filled_quantity > self.quantity:
            raise DomainValidationError(
                f"filled_quantity ({self.filled_quantity}) cannot exceed "
                f"quantity ({self.quantity}).",
                field="filled_quantity",
                code=ErrorCode.VALIDATION_ERROR,
            )
        return self


class FillEvent(BaseModel):
    """An executed order fill event emitted by the simulator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fill_id: str = Field(..., min_length=1, max_length=64)
    order_id: str = Field(..., min_length=1, max_length=64)
    instrument_id: int = Field(..., ge=1)
    symbol: str = Field(..., min_length=1, max_length=20)
    timestamp: datetime = Field(..., description="Timestamp when fill occurred (UTC)")
    fill_price: Decimal = Field(..., gt=Decimal("0"))
    fill_quantity: int = Field(..., ge=1)
    side: OrderSide = Field(...)
    cost_breakdown: CostBreakdown = Field(...)
    is_partial: bool = Field(default=False)
    is_gap_fill: bool = Field(
        default=False, description="True if filled at market gap beyond specified price"
    )
    is_ambiguous_exit: bool = Field(
        default=False, description="True if both target and stop were hit in same bar"
    )
    ambiguity_treatment: AmbiguityTreatment = Field(default=AmbiguityTreatment.NONE)
    mode: DataMode = Field(default=DataMode.HISTORICAL_REPLAY)

    @field_validator("timestamp", mode="before")
    @classmethod
    def normalize_fill_timestamp(cls, v: Any) -> datetime:
        return normalize_to_utc(v)


class PositionState(BaseModel):
    """State of an open or closed position."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    portfolio_id: int = Field(..., ge=1)
    instrument_id: int = Field(..., ge=1)
    symbol: str = Field(..., min_length=1, max_length=20)
    quantity: int = Field(
        default=0, ge=0, description="Long-only equity: non-negative integer shares"
    )
    average_entry_price: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0"))
    current_mark_price: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0"))
    realized_pnl: Decimal = Field(default=Decimal("0.0000"))
    unrealized_pnl: Decimal = Field(default=Decimal("0.0000"))
    total_cost_accrued: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0"))
    entry_timestamp: datetime
    last_update_timestamp: datetime
    stop_loss: Decimal = Field(..., gt=Decimal("0"))
    target_price: Decimal = Field(..., gt=Decimal("0"))
    max_holding_bars: int = Field(default=75, ge=1)
    bars_held: int = Field(default=0, ge=0)
    status: str = Field(default="OPEN")  # OPEN, CLOSED, UNRESOLVED
    mode: DataMode = Field(default=DataMode.HISTORICAL_REPLAY)

    @field_validator("entry_timestamp", "last_update_timestamp", mode="before")
    @classmethod
    def normalize_position_timestamps(cls, v: Any) -> datetime:
        return normalize_to_utc(v)


class PortfolioState(BaseModel):
    """Point-in-time state of the portfolio with cash reservations and accounting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: int = Field(..., ge=1)
    portfolio_id: int = Field(..., ge=1)
    initial_scenario_capital: Decimal = Field(
        default=Decimal("30000.00"), gt=Decimal("0"), description="Default ₹30,000 scenario"
    )
    available_cash: Decimal = Field(default=Decimal("30000.00"))
    reserved_cash: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    total_equity: Decimal = Field(default=Decimal("30000.00"))
    positions: dict[int, PositionState] = Field(default_factory=dict)
    open_orders: dict[str, ExecutionOrder] = Field(default_factory=dict)
    realized_pnl: Decimal = Field(default=Decimal("0.0000"))
    total_costs_paid: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0"))
    mode: DataMode = Field(default=DataMode.HISTORICAL_REPLAY)


class SimulatedTradeResult(BaseModel):
    """A completed simulated trade lifecycle for reporting and performance measurement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trade_id: str
    instrument_id: int
    symbol: str
    quantity: int
    entry_timestamp: datetime
    exit_timestamp: datetime
    entry_price: Decimal
    exit_price: Decimal
    exit_reason: str  # TARGET, STOP_LOSS, GAP_STOP, SESSION_CUTOFF, MAX_HOLDING, UNRESOLVED
    gross_pnl: Decimal
    entry_costs: CostBreakdown
    exit_costs: CostBreakdown
    total_costs: Decimal
    net_pnl: Decimal
    return_pct: Decimal
    is_ambiguous_exit: bool = False
    ambiguity_treatment: AmbiguityTreatment = AmbiguityTreatment.NONE
    mode: DataMode = DataMode.HISTORICAL_REPLAY

    @field_validator("entry_timestamp", "exit_timestamp", mode="before")
    @classmethod
    def normalize_trade_timestamps(cls, v: Any) -> datetime:
        return normalize_to_utc(v)
