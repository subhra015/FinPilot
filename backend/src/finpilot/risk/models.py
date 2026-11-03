"""Domain models and authorization schemas for the Independent Risk Engine (Layer 11).

Governed by:
- PROJECT_SPEC.md §4, §5, §7
- DATA_AND_PERFORMANCE_POLICY.md §2, §7
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-09, SEC-19
- Layer 11 Gate: Independent risk authority, explicit authorization contracts, deny-by-default,
  tamper-evident audit trail, and zero bypass by ML models.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from finpilot.db.enums import OrderSide
from finpilot.schemas.common import normalize_to_utc


class RiskDecisionStatus(StrEnum):
    """Terminal decision status issued by the independent risk authority."""

    AUTHORIZED = "AUTHORIZED"
    REJECTED = "REJECTED"
    CIRCUIT_BROKEN = "CIRCUIT_BROKEN"
    SUSPENDED = "SUSPENDED"


class RiskRejectionReason(StrEnum):
    """Machine-readable denial reasons for automated risk filtering."""

    # Data & Session
    DATA_STALE_OR_MISSING = "DATA_STALE_OR_MISSING"
    MARKET_DATA_INVALID = "MARKET_DATA_INVALID"
    OUT_OF_SESSION = "OUT_OF_SESSION"
    SESSION_ENTRY_CUTOFF = "SESSION_ENTRY_CUTOFF"

    # Governance & Policy Versioning
    UNSUPPORTED_INSTRUMENT = "UNSUPPORTED_INSTRUMENT"
    TRADING_MODE_DISABLED = "TRADING_MODE_DISABLED"
    POLICY_VERSION_MISMATCH = "POLICY_VERSION_MISMATCH"
    MODEL_VERSION_MISMATCH = "MODEL_VERSION_MISMATCH"

    # Capital & Sizing
    INSUFFICIENT_AVAILABLE_CASH = "INSUFFICIENT_AVAILABLE_CASH"
    AFFORDABILITY_CHECK_FAILED = "AFFORDABILITY_CHECK_FAILED"
    NON_POSITIVE_QUANTITY = "NON_POSITIVE_QUANTITY"

    # Risk & Limits
    EXCESSIVE_STOP_RISK = "EXCESSIVE_STOP_RISK"
    INSUFFICIENT_ADVERSE_EXECUTION_BUFFER = "INSUFFICIENT_ADVERSE_EXECUTION_BUFFER"
    POSITION_EXPOSURE_CAP_EXCEEDED = "POSITION_EXPOSURE_CAP_EXCEEDED"
    TOTAL_EXPOSURE_CAP_EXCEEDED = "TOTAL_EXPOSURE_CAP_EXCEEDED"
    CONCENTRATION_LIMIT_EXCEEDED = "CONCENTRATION_LIMIT_EXCEEDED"
    MAX_CONCURRENT_POSITIONS_EXCEEDED = "MAX_CONCURRENT_POSITIONS_EXCEEDED"

    # Circuit Breakers & Suspension
    DAILY_LOSS_LIMIT_EXCEEDED = "DAILY_LOSS_LIMIT_EXCEEDED"
    DRAWDOWN_SUSPENSION_TRIGGERED = "DRAWDOWN_SUSPENSION_TRIGGERED"

    # Order & Position Hygiene
    DUPLICATE_SIGNAL_OR_ORDER = "DUPLICATE_SIGNAL_OR_ORDER"
    UNRESOLVED_POSITION_STATE = "UNRESOLVED_POSITION_STATE"
    INVALID_PRICE_RELATIONSHIP = "INVALID_PRICE_RELATIONSHIP"

    # Administrative Controls
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    MANUAL_TRADING_PAUSED = "MANUAL_TRADING_PAUSED"
    UNAUTHORIZED_ROLE = "UNAUTHORIZED_ROLE"


class RiskAuthorization(BaseModel):
    """Cryptographically sealed authorization token required for order placement.

    SEC-06 & SEC-19: A simulator or broker interface MUST reject any order or proposal
    lacking this exact authorization matching proposal_id, model_id, and policy_version.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    authorization_id: str = Field(..., min_length=5, max_length=100)
    proposal_id: str = Field(..., min_length=1, max_length=100)
    model_id: str = Field(..., min_length=1, max_length=100)
    policy_version: str = Field(default="TP-V1", max_length=50)
    symbol: str = Field(..., min_length=1, max_length=20)
    instrument_id: int = Field(..., ge=1)
    side: OrderSide = Field(default=OrderSide.BUY)
    authorized_quantity: int = Field(..., ge=1, le=1000000, description="Integer shares only")
    allocated_capital: Decimal = Field(..., gt=Decimal("0.00"))
    max_adverse_entry_price: Decimal = Field(..., gt=Decimal("0.00"))
    stop_loss_limit: Decimal = Field(..., gt=Decimal("0.00"))
    target_price_limit: Decimal = Field(..., gt=Decimal("0.00"))
    authorized_at: datetime
    expires_at: datetime
    auth_signature: str = Field(..., description="SHA-256 seal of authorization fields")

    @field_validator("authorized_at", "expires_at", mode="before")
    @classmethod
    def validate_utc(cls, v: Any) -> datetime:
        return normalize_to_utc(v)

    def verify_signature(self) -> bool:
        """Verify the cryptographic SHA-256 seal of this authorization."""
        expected = self.compute_signature()
        return self.auth_signature == expected

    def compute_signature(self) -> str:
        """Compute the deterministic SHA-256 seal over critical parameters."""
        data = (
            f"{self.authorization_id}|{self.proposal_id}|{self.model_id}|{self.policy_version}|"
            f"{self.symbol}|{self.instrument_id}|{self.side.value}|{self.authorized_quantity}|"
            f"{self.allocated_capital}|{self.max_adverse_entry_price}|{self.stop_loss_limit}|"
            f"{self.target_price_limit}|{self.authorized_at.isoformat()}|{self.expires_at.isoformat()}"
        )
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @classmethod
    def create(
        cls,
        authorization_id: str,
        proposal_id: str,
        model_id: str,
        symbol: str,
        instrument_id: int,
        authorized_quantity: int,
        allocated_capital: Decimal,
        max_adverse_entry_price: Decimal,
        stop_loss_limit: Decimal,
        target_price_limit: Decimal,
        authorized_at: datetime,
        expires_at: datetime,
        policy_version: str = "TP-V1",
        side: OrderSide = OrderSide.BUY,
    ) -> RiskAuthorization:
        """Factory creating and signing a RiskAuthorization."""
        auth = cls(
            authorization_id=authorization_id,
            proposal_id=proposal_id,
            model_id=model_id,
            policy_version=policy_version,
            symbol=symbol,
            instrument_id=instrument_id,
            side=side,
            authorized_quantity=authorized_quantity,
            allocated_capital=allocated_capital,
            max_adverse_entry_price=max_adverse_entry_price,
            stop_loss_limit=stop_loss_limit,
            target_price_limit=target_price_limit,
            authorized_at=authorized_at,
            expires_at=expires_at,
            auth_signature="temp",
        )
        return auth.model_copy(update={"auth_signature": auth.compute_signature()})


class RiskMetricsSnapshot(BaseModel):
    """Telemetry capturing current portfolio risk state at decision time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    available_cash: Decimal = Field(..., ge=Decimal("0.00"))
    total_equity: Decimal = Field(..., ge=Decimal("0.00"))
    current_position_count: int = Field(..., ge=0)
    daily_realized_loss: Decimal = Field(..., ge=Decimal("0.00"))
    current_drawdown_pct: float = Field(..., ge=0.0)
    current_instrument_exposure: Decimal = Field(default=Decimal("0.00"))


class RiskEvaluationResult(BaseModel):
    """Comprehensive evaluation record returned by the Risk Engine."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str = Field(..., min_length=5, max_length=100)
    status: RiskDecisionStatus
    authorization: RiskAuthorization | None = Field(default=None)
    rejection_reasons: list[RiskRejectionReason] = Field(default_factory=list)
    rejection_details: list[str] = Field(default_factory=list)
    metrics_snapshot: RiskMetricsSnapshot
    evaluated_at: datetime

    @field_validator("evaluated_at", mode="before")
    @classmethod
    def validate_utc(cls, v: Any) -> datetime:
        return normalize_to_utc(v)


class RiskConfig(BaseModel):
    """Immutable, centralized risk configuration containing conservative static caps.

    SEC-01 & SEC-09: Only authorized administrators can update risk limits. Normal users
    and frontend payloads are strictly prohibited from changing or bypassing limits.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    config_version: str = Field(default="RISK-CFG-V1", max_length=50)
    max_account_equity: Decimal = Field(default=Decimal("30000.00"), gt=Decimal("0.00"))
    max_exposure_per_instrument_pct: Decimal = Field(
        default=Decimal("0.50"), ge=Decimal("0.01"), le=Decimal("1.00")
    )
    max_total_exposure_pct: Decimal = Field(
        default=Decimal("1.00"), ge=Decimal("0.01"), le=Decimal("1.00")
    )
    max_concurrent_positions: int = Field(default=1, ge=1, le=10)
    max_planned_stop_risk_pct: Decimal = Field(
        default=Decimal("0.02"), ge=Decimal("0.001"), le=Decimal("0.10")
    )
    max_slippage_buffer_bps: Decimal = Field(
        default=Decimal("10.0"), ge=Decimal("0.0"), le=Decimal("100.0")
    )
    max_daily_loss: Decimal = Field(default=Decimal("1500.00"), gt=Decimal("0.00"))
    max_drawdown_pct: float = Field(default=0.10, ge=0.01, le=0.50)
    session_entry_cutoff_ist: str = Field(default="15:00:00")
    forced_exit_cutoff_ist: str = Field(default="15:15:00")
    max_candle_staleness_seconds: int = Field(default=300, ge=60, le=3600)
    approved_instruments: list[str] = Field(
        default_factory=lambda: ["RELIANCE", "TCS", "INFY"]
    )
    approved_policy_version: str = Field(default="TP-V1", max_length=50)
    approved_model_ids: list[str] = Field(
        default_factory=lambda: ["MODEL-LOGREG-V1", "MODEL-LIGHTGBM-V1", "STRAT-SIMPLE-V1"]
    )
    kill_switch_active: bool = Field(default=False)
    manual_trading_paused: bool = Field(default=False)
    updated_by_role: str = Field(default="admin", max_length=50)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("updated_at", mode="before")
    @classmethod
    def validate_utc(cls, v: Any) -> datetime:
        return normalize_to_utc(v)

    def calculate_config_hash(self) -> str:
        """Calculate deterministic SHA-256 hash of this risk configuration."""
        dumped = self.model_dump(mode="json")
        dumped.pop("updated_at", None)
        canonical = json.dumps(dumped, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RiskConfigAuditEvent(BaseModel):
    """Immutable audit trail event logged when risk configuration is modified.

    SEC-08 & SEC-09: Every administrative modification is signed, attributed, and stored.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_id: str = Field(..., min_length=5, max_length=100)
    timestamp: datetime
    user_id: str = Field(..., min_length=1, max_length=100)
    user_role: str = Field(..., min_length=1, max_length=50)
    action: str = Field(..., min_length=1, max_length=100)
    previous_config_hash: str = Field(...)
    new_config_hash: str = Field(...)
    changed_fields: dict[str, Any] = Field(default_factory=dict)
    audit_signature: str = Field(...)

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_utc(cls, v: Any) -> datetime:
        return normalize_to_utc(v)

    def compute_signature(self) -> str:
        """Compute the deterministic SHA-256 seal for this audit event."""
        canonical_changes = json.dumps(self.changed_fields, sort_keys=True)
        raw = (
            f"{self.audit_id}|{self.timestamp.isoformat()}|{self.user_id}|{self.user_role}|{self.action}|"
            f"{self.previous_config_hash}|{self.new_config_hash}|{canonical_changes}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def verify_signature(self) -> bool:
        """Verify the cryptographic SHA-256 seal of this audit event."""
        return self.audit_signature == self.compute_signature()

    @classmethod
    def create(
        cls,
        audit_id: str,
        user_id: str,
        user_role: str,
        action: str,
        previous_config_hash: str,
        new_config_hash: str,
        changed_fields: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> RiskConfigAuditEvent:
        """Factory creating and signing an audit event."""
        ts = timestamp or datetime.now(UTC)
        canonical_changes = json.dumps(changed_fields, sort_keys=True)
        raw = (
            f"{audit_id}|{ts.isoformat()}|{user_id}|{user_role}|{action}|"
            f"{previous_config_hash}|{new_config_hash}|{canonical_changes}"
        )
        sig = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return cls(
            audit_id=audit_id,
            timestamp=ts,
            user_id=user_id,
            user_role=user_role,
            action=action,
            previous_config_hash=previous_config_hash,
            new_config_hash=new_config_hash,
            changed_fields=changed_fields,
            audit_signature=sig,
        )


class PositionCloseIntent(BaseModel):
    """Represents an intent to close an existing open position (Exit).

    Distinguished from new entry proposals: exits do not check cash affordability,
    entry cutoffs, or max concurrent positions.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    close_id: str = Field(..., min_length=1, max_length=100)
    instrument_id: int = Field(..., ge=1)
    symbol: str = Field(..., min_length=1, max_length=20)
    quantity_to_close: int = Field(..., ge=1)
    timestamp: datetime
    reason: str = Field(default="SESSION_SQUARE_OFF")

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_utc(cls, v: Any) -> datetime:
        return normalize_to_utc(v)
