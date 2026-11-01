"""Trade policy versioning and long-only trade proposal contracts (TP-V1, Layer 3).

Enforces:
- Fixed policy versioning (TP-V1).
- Decision-time rules based on completed 5-minute candles only.
- Long-only equity invariants: stop_loss < entry_price < target_price.
- Causal execution timing: earliest_entry_timestamp > decision_timestamp.
- Whole integer share quantities (no fractional shares).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from finpilot.db.enums import DataMode, OrderSide

from .common import normalize_to_utc
from .errors import DomainValidationError, ErrorCode


class TradePolicyV1Contract(BaseModel):
    """Specification of the TP-V1 Trade Policy contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: str = Field(default="TP-V1", max_length=20)
    decision_timestamp_rule: str = Field(default="completed_5m_candle", max_length=50)
    mode: DataMode = Field(default=DataMode.HISTORICAL_REPLAY)
    max_position_pct_equity: Decimal = Field(default=Decimal("1.0000"), ge=Decimal("0.01"))
    enforce_long_only: bool = Field(default=True)
    allow_short_selling: bool = Field(default=False)
    allow_derivatives: bool = Field(default=False)
    allow_leverage: bool = Field(default=False)

    @field_validator(
        "enforce_long_only",
        "allow_short_selling",
        "allow_derivatives",
        "allow_leverage",
    )
    @classmethod
    def check_v1_constraints(cls, v: bool, info: Any) -> bool:
        if info.field_name == "enforce_long_only" and not v:
            raise DomainValidationError("V1 Trade Policy must enforce long-only equities.")
        if info.field_name in ("allow_short_selling", "allow_derivatives", "allow_leverage") and v:
            raise DomainValidationError(f"V1 Trade Policy prohibits {info.field_name}.")
        return v


class TradeProposal(BaseModel):
    """A proposed trade emitted by the research model/strategy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_id: str = Field(..., min_length=1, max_length=64)
    policy_version: str = Field(default="TP-V1", max_length=20)
    instrument_id: int = Field(..., ge=1)
    symbol: str = Field(..., min_length=1, max_length=20)
    decision_timestamp: datetime = Field(
        ..., description="Completed 5m decision candle timestamp (UTC)"
    )
    earliest_entry_timestamp: datetime = Field(
        ..., description="Earliest execution event timestamp (UTC)"
    )
    entry_price: Decimal = Field(..., gt=Decimal("0"), le=Decimal("10000000.0000"))
    stop_loss: Decimal = Field(..., gt=Decimal("0"), le=Decimal("10000000.0000"))
    target_price: Decimal = Field(..., gt=Decimal("0"), le=Decimal("10000000.0000"))
    quantity: int = Field(..., ge=1, le=1000000, description="Integer share quantity only")
    side: OrderSide = Field(default=OrderSide.BUY, description="Long-only equity V1: BUY to enter")
    mode: DataMode = Field(default=DataMode.HISTORICAL_REPLAY)

    @field_validator("decision_timestamp", "earliest_entry_timestamp", mode="before")
    @classmethod
    def normalize_proposal_timestamps(cls, v: Any) -> datetime:
        return normalize_to_utc(v)

    @model_validator(mode="after")
    def validate_long_only_price_relationships_and_time(self) -> TradeProposal:
        # Long-only rule: stop_loss must be below entry_price
        if self.stop_loss >= self.entry_price:
            raise DomainValidationError(
                f"Long-only trade proposal violation: Stop loss ({self.stop_loss}) "
                f"must be strictly less than entry price ({self.entry_price}).",
                field="stop_loss",
                code=ErrorCode.VALIDATION_ERROR,
            )

        # Long-only rule: target_price must be above entry_price
        if self.target_price <= self.entry_price:
            raise DomainValidationError(
                f"Long-only trade proposal violation: Target price ({self.target_price}) "
                f"must be strictly greater than entry price ({self.entry_price}).",
                field="target_price",
                code=ErrorCode.VALIDATION_ERROR,
            )

        # Earliest entry must be strictly after decision timestamp
        if self.earliest_entry_timestamp <= self.decision_timestamp:
            raise DomainValidationError(
                f"Timing violation: earliest_entry_timestamp "
                f"({self.earliest_entry_timestamp.isoformat()}) must be strictly greater "
                f"than decision_timestamp ({self.decision_timestamp.isoformat()}).",
                field="earliest_entry_timestamp",
                code=ErrorCode.VALIDATION_ERROR,
            )

        return self
