"""Domain models and schemas for forward paper trading and live validation (Layer 16).

Governed by:
- ACCEPTANCE_GATES.md §2 (Layer 16 Gate)
- DATA_AND_PERFORMANCE_POLICY.md §3 (Execution Modes), §7 (Statistical Rigor)
- PROJECT_SPEC.md §3, §4, §5, §7, §9, §11
- SECURITY_CHECKLIST.md SEC-01 through SEC-27
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from finpilot.db.enums import DataMode
from finpilot.schemas.common import normalize_to_utc


class ForwardDecision(StrEnum):
    """Supported candidate decision outcomes in the forward paper trading engine."""

    ACCEPTED = "ACCEPTED"
    NO_TRADE = "NO_TRADE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    RISK_REJECTED = "RISK_REJECTED"
    ENTRY_UNFILLED = "ENTRY_UNFILLED"
    EXECUTION_UNRESOLVED = "EXECUTION_UNRESOLVED"


class VirtualCapitalTier(StrEnum):
    """Supported virtual starting capital tiers for forward paper evaluation."""

    TIER_2K = "TIER_2K"       # ₹2,000 (Micro / Integer-share constraint demonstrator)
    TIER_10K = "TIER_10K"     # ₹10,000 (Small)
    TIER_30K = "TIER_30K"     # ₹30,000 (Baseline evaluation)
    TIER_50K = "TIER_50K"     # ₹50,000 (Standard intraday)
    CUSTOM = "CUSTOM"         # User-specified cash


class VirtualPortfolioConfig(BaseModel):
    """User-controlled virtual portfolio starting configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tier: VirtualCapitalTier = VirtualCapitalTier.TIER_30K
    initial_capital: Decimal = Field(..., gt=Decimal("0.00"), description="Virtual starting cash in INR")
    max_open_positions: int = Field(default=1, ge=1, le=5)
    portfolio_name: str = "Forward Paper Portfolio"
    mode: DataMode = Field(default=DataMode.FORWARD_PAPER)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str = Field(
        default=(
            "₹30,000 is a demonstration baseline only, not a mandatory minimum or investment advice. "
            "Server-authoritative risk and integer-share affordability are enforced regardless of portfolio size."
        )
    )

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_utc(cls, v: Any) -> datetime:
        return normalize_to_utc(v)


class ModelIntegrityVerification(BaseModel):
    """Cryptographic verification evidence for the frozen Layer 15 model and configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str
    expected_artifact_checksum: str
    actual_artifact_checksum: str
    is_checksum_verified: bool
    feature_schema_version: str
    calibration_policy_id: str
    calibration_policy_hash: str
    is_policy_verified: bool
    decision_threshold: float
    policy_version: str
    risk_config_version: str
    verified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PredictionEventRecord(BaseModel):
    """Append-only Prediction Ledger record capturing candidate state before and after outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Prediction Identifiers and Timestamps (Recorded BEFORE outcome is known)
    event_id: str = Field(..., min_length=1, max_length=100)
    prediction_timestamp: datetime
    candle_timestamp: datetime
    data_provider: str = "SYNTHETIC_DEMO_GEN"
    symbol: str
    instrument_id: int
    feature_version: str = "FS-V1"
    features_snapshot: dict[str, float] | None = None
    model_id: str
    model_hash: str

    # Prediction & Expectancy Metrics
    raw_probability: float | None = None
    calibrated_probability: float | None = None
    estimated_expectancy: Decimal | None = None

    # Proposed Trade Parameters
    proposed_entry_price: Decimal
    stop_loss_price: Decimal
    profit_target_price: Decimal
    requested_quantity: int
    authorized_quantity: int = 0

    # Risk Engine Assessment
    risk_authorized: bool
    risk_authorization_id: str | None = None
    risk_rejection_reasons: list[str] = Field(default_factory=list)

    # Decision State
    decision: ForwardDecision
    decision_reason: str

    # Execution State (Appended when order/fill occurs, never overwriting prediction)
    paper_order_id: str | None = None
    fill_price: Decimal | None = None
    fill_quantity: int | None = None
    fill_timestamp: datetime | None = None
    slippage_incurred: Decimal = Decimal("0.00")
    charges_incurred: Decimal = Decimal("0.00")

    # Terminal Outcome State (Appended when position exits or expires)
    exit_price: Decimal | None = None
    exit_timestamp: datetime | None = None
    exit_reason: str | None = None
    gross_pnl: Decimal = Decimal("0.00")
    net_pnl: Decimal = Decimal("0.00")

    # Audit & Mode Tags (Strict separation of modes)
    is_backtest_outcome: bool = False
    execution_mode: str = "FORWARD_PAPER"

    @field_validator(
        "prediction_timestamp",
        "candle_timestamp",
        "fill_timestamp",
        "exit_timestamp",
        mode="before",
    )
    @classmethod
    def validate_utc_fields(cls, v: Any) -> datetime | None:
        if v is None:
            return None
        return normalize_to_utc(v)


class ForwardPaperStatus(BaseModel):
    """Live state summary of forward paper trading runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: str = "FORWARD_PAPER"
    initial_capital: Decimal
    current_equity: Decimal
    available_cash: Decimal
    reserved_cash: Decimal
    open_positions_count: int
    active_orders_count: int
    total_predictions_recorded: int
    total_trades_completed: int
    realized_net_pnl: Decimal
    unrealized_pnl: Decimal
    is_safe_mode_active: bool = False
    safe_mode_reason: str | None = None
    last_candle_timestamp: datetime | None = None
    system_clock_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DriftMonitorMetrics(BaseModel):
    """Real-time data quality, latency, and drift metrics for forward monitoring."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candles_processed: int
    data_latency_seconds_max: float
    data_latency_seconds_avg: float
    stale_feed_incidents: int
    abnormal_geometry_incidents: int
    out_of_distribution_count: int
    safe_no_new_entry_mode: bool
    safe_mode_trigger_reason: str | None = None
    rolling_drawdown_pct: float
    empirical_win_rate_pct: float
    calibrated_predicted_win_rate_pct: float
    calibration_drift_delta: float
    accounting_discrepancy: Decimal = Decimal("0.00")


class ForwardPerformanceMetrics(BaseModel):
    """Aggregate forward paper performance metrics with uncertainty intervals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    starting_equity: Decimal
    ending_equity: Decimal
    gross_pnl: Decimal
    total_fees: Decimal
    net_pnl: Decimal
    net_return_pct: float
    net_expectancy_per_trade: Decimal
    profit_factor: float
    profit_factor_formula: str = "Sum(Gains) / Abs(Sum(Losses))"
    win_rate_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    scratch_trades: int
    max_drawdown_pct: float
    worst_trading_day: Decimal
    longest_losing_streak: int
    monthly_returns: dict[str, float]
    signals_evaluated: int
    signals_accepted: int
    coverage_rate: float
    ci_net_pnl_95: tuple[float, float]
    ci_expectancy_95: tuple[float, float]
    data_quality_failures: int
