"""Cost calculation, order, and position state schemas (Layer 0, Layer 3).

Enforces:
- Detailed Indian regulatory cost breakdown (STT, exchange, SEBI, GST, stamp duty, slippage).
- Non-negative financial fees and prices.
- Long-only position constraints (quantity >= 0).
- Order constraints (quantity >= 1, filled_quantity <= quantity).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from finpilot.db.enums import DataMode, OrderSide, OrderStatus, OrderType

from .common import normalize_to_utc
from .errors import DomainValidationError, ErrorCode


class CostBreakdown(BaseModel):
    """Detailed transaction and statutory cost breakdown in INR."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    brokerage: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0"))
    stt: Decimal = Field(
        default=Decimal("0.0000"), ge=Decimal("0"), description="Securities Transaction Tax"
    )
    exchange_charges: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0"))
    sebi_turnover_fee: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0"))
    stamp_duty: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0"))
    gst: Decimal = Field(
        default=Decimal("0.0000"), ge=Decimal("0"), description="18% GST on services"
    )
    modelled_slippage: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0"))
    total_costs: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0"))

    @model_validator(mode="after")
    def compute_total_if_zero(self) -> CostBreakdown:
        computed = (
            self.brokerage
            + self.stt
            + self.exchange_charges
            + self.sebi_turnover_fee
            + self.stamp_duty
            + self.gst
            + self.modelled_slippage
        )
        if self.total_costs == Decimal("0") and computed > Decimal("0"):
            object.__setattr__(self, "total_costs", computed)
        return self


class OrderBase(BaseModel):
    """Base order properties."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    portfolio_id: int = Field(..., ge=1)
    instrument_id: int = Field(..., ge=1)
    order_type: OrderType = Field(default=OrderType.MARKET)
    side: OrderSide = Field(default=OrderSide.BUY)
    quantity: int = Field(..., ge=1, le=1000000, description="Integer share quantity only")
    filled_quantity: int = Field(default=0, ge=0)
    price: Decimal | None = Field(default=None, gt=Decimal("0"), le=Decimal("10000000.0000"))
    status: OrderStatus = Field(default=OrderStatus.PENDING)
    risk_authorization_id: str | None = Field(default=None, max_length=100)
    mode: DataMode = Field(default=DataMode.HISTORICAL_REPLAY)

    @model_validator(mode="after")
    def validate_order_quantities(self) -> OrderBase:
        if self.filled_quantity > self.quantity:
            raise DomainValidationError(
                f"filled_quantity ({self.filled_quantity}) cannot exceed "
                f"total order quantity ({self.quantity}).",
                field="filled_quantity",
                code=ErrorCode.VALIDATION_ERROR,
            )
        return self


class OrderCreate(OrderBase):
    """Payload to submit an order."""

    id: str = Field(..., min_length=1, max_length=64)


class OrderRead(OrderBase):
    """Read representation of an order."""

    id: str
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def normalize_order_timestamps(cls, v: Any) -> datetime:
        return normalize_to_utc(v)


class PositionRead(BaseModel):
    """Read representation of an operational position (long-only equity cash)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    portfolio_id: int = Field(..., ge=1)
    instrument_id: int = Field(..., ge=1)
    quantity: int = Field(
        default=0, ge=0, description="Long-only equity: non-negative integer shares"
    )
    average_entry_price: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0"))
    current_price: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0"))
    realized_pnl: Decimal = Field(default=Decimal("0.0000"))
    unrealized_pnl: Decimal = Field(default=Decimal("0.0000"))
    mode: DataMode = Field(default=DataMode.HISTORICAL_REPLAY)
    updated_at: datetime

    @field_validator("updated_at", mode="before")
    @classmethod
    def normalize_pos_timestamp(cls, v: Any) -> datetime:
        return normalize_to_utc(v)
