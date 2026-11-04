"""Data schemas for locked historical evaluation and user trust (Layer 15).

Governed by:
- ACCEPTANCE_GATES.md §2 (Layer 15 Gate)
- DATA_AND_PERFORMANCE_POLICY.md §7 (Evaluation Hygiene)
- PROJECT_SPEC.md §4, §5, §7, §9
- SECURITY_CHECKLIST.md SEC-06, SEC-19
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EconomicVerdictEnum(StrEnum):
    """Predeclared economic verdict categories per Layer 15 specification."""

    EDGE_SUPPORTED_UNDER_TESTED_ASSUMPTIONS = "EDGE SUPPORTED UNDER TESTED ASSUMPTIONS"
    SUGGESTIVE_BUT_INCONCLUSIVE = "SUGGESTIVE BUT INCONCLUSIVE"
    NO_DEMONSTRATED_EDGE = "NO DEMONSTRATED EDGE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT EVIDENCE"
    INVALID_EVALUATION = "INVALID EVALUATION"


class DatasetManifest(BaseModel):
    """Metadata describing the historical market dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_name: str
    dataset_hash: str
    publisher: str
    license_status: str
    permitted_uses: list[str]
    total_bars: int
    start_date: str
    end_date: str
    universe: list[str]


class ModelFreezeMetadata(BaseModel):
    """Cryptographic freeze metadata for the evaluated model and decision policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str
    artifact_checksum: str
    model_family: str
    feature_schema_version: str
    feature_names: list[str]
    hyperparameters: dict[str, Any]
    calibration_policy_id: str
    calibration_policy_hash: str
    decision_threshold: float
    git_commit: str


class CostScheduleMetadata(BaseModel):
    """Statutory cost schedule parameters under evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schedule_name: str
    brokerage_rate: float
    stt_rate: float
    exchange_txn_rate: float
    sebi_rate: float
    stamp_duty_rate: float
    gst_rate: float
    default_slippage_bps: float


class EvaluationManifest(BaseModel):
    """Immutable evaluation manifest created prior to unsealing locked test outcomes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_id: str
    created_at: datetime
    git_commit: str
    dataset_manifest: DatasetManifest
    split_manifest_id: str
    locked_final_test_hash: str
    model_freeze: ModelFreezeMetadata
    cost_schedule: CostScheduleMetadata
    simulator_version: str
    virtual_capital_tiers: list[Decimal]
    evaluation_period_start: str
    evaluation_period_end: str
    manifest_sha256: str


class TradeValidationRecord(BaseModel):
    """Transparent trade execution record allowing users to inspect and validate decision logic."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trade_id: str
    opportunity_id: str
    symbol: str
    signal_timestamp: datetime
    market_data_timestamp: datetime
    market_data_provenance: str
    model_version: str
    raw_probability: float | None = None
    calibrated_probability: float | None = None
    estimated_expectancy: Decimal | None = None
    proposed_entry_price: Decimal
    stop_loss_price: Decimal
    profit_target_price: Decimal
    requested_quantity: int
    authorized_quantity: int
    estimated_fees: Decimal
    risk_authorized: bool
    risk_rejection_reasons: list[str] = Field(default_factory=list)
    decision_state: str
    fill_price: Decimal | None = None
    exit_price: Decimal | None = None
    exit_timestamp: datetime | None = None
    exit_reason: str | None = None
    gross_pnl: Decimal = Decimal("0.00")
    net_pnl: Decimal = Decimal("0.00")
    fees_paid: Decimal = Decimal("0.00")
    execution_mode: str = "HISTORICAL_REPLAY"
    is_backtest_outcome: bool = True


class UncertaintyInterval(BaseModel):
    """Dependence-aware statistical bootstrap confidence interval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    point_estimate: float
    ci_lower_95: float
    ci_upper_95: float
    std_err: float
    method: str = "date_clustered_block_bootstrap_b1000"


class BrierDecomposition(BaseModel):
    """Murphy (1973) Brier score resolution and calibration decomposition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    brier_score: float
    reliability: float  # Pure calibration component (lower is better, 0 is perfect)
    resolution: float   # Discrimination component (higher is better)
    uncertainty: float  # Base rate entropy component: o_bar * (1 - o_bar)
    log_loss: float
    identity_holds: bool = True
    explanation: str = (
        "Brier score = Reliability - Resolution + Uncertainty. Brier score is not a pure "
        "calibration measure because it conflates calibration (reliability) with discrimination "
        "(resolution) and irreducible problem uncertainty."
    )


class SlippageSensitivityResult(BaseModel):
    """Evaluation sensitivity across varying execution slippage assumptions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slippage_bps: float
    gross_pnl: Decimal
    fees: Decimal
    net_pnl: Decimal
    expectancy: Decimal
    profit_factor: float


class ArmPerformanceMetrics(BaseModel):
    """Standardized performance metrics for an evaluation arm."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    arm_id: str
    arm_name: str
    initial_capital: Decimal
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
    losing_streak: int
    monthly_returns: dict[str, float]
    capital_utilization_pct: float
    signals_evaluated: int
    signals_accepted: int
    coverage_rate: float
    fee_breakdown: dict[str, Decimal]
    brier_decomposition: BrierDecomposition | None = None
    bootstrap_ci_net_pnl: UncertaintyInterval
    bootstrap_ci_expectancy: UncertaintyInterval
    bootstrap_ci_win_rate: UncertaintyInterval
    slippage_sensitivity: list[SlippageSensitivityResult] = Field(default_factory=list)


class CapitalScenarioEvaluation(BaseModel):
    """Performance evaluation across user-configurable virtual capital levels."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capital: Decimal
    affordable_trades: int
    capital_rejected_trades: int
    net_pnl: Decimal
    net_return_pct: float
    max_drawdown_pct: float
    hurdle_band_met: bool
    notes: str


class EconomicVerdict(BaseModel):
    """Predeclared economic verdict and justification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: EconomicVerdictEnum
    research_integrity_passed: bool
    economic_edge_demonstrated: bool
    incremental_net_pnl_vs_simple: Decimal
    incremental_win_rate_vs_simple: float
    p_value_or_confidence: str
    justification: str


class LockedHistoricalEvaluationReport(BaseModel):
    """Comprehensive, tamper-evident locked evaluation report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: EvaluationManifest
    arm_a_no_trade: ArmPerformanceMetrics
    arm_b_simple_baseline: ArmPerformanceMetrics
    arm_c_ml_selected: ArmPerformanceMetrics
    incremental_contribution: dict[str, Any]
    capital_scenarios: list[CapitalScenarioEvaluation]
    user_validation_sample: list[TradeValidationRecord]
    total_validation_records: int
    data_and_leakage_audit: dict[str, Any]
    known_limitations: list[str]
    economic_verdict: EconomicVerdict
