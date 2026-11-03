"""Domain models and schemas for probability calibration and selective decisions (Layer 10).

Governed by:
- PROJECT_SPEC.md §4, §5, §7, §9
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 10 Gate: Calibration on designated partitions, reliability diagrams, proper scoring
  rule decomposition, explicit 5-state selective decisions, sample support & OOD abstention,
  expectancy estimation without double cost deduction, and frozen decision policy.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from finpilot.schemas.common import normalize_to_utc


class DecisionState(StrEnum):
    """Explicit selective decision states for trade proposal evaluation (Layer 10).

    A model score alone must NEVER authorize a portfolio entry. The selective decision
    engine emits an evaluated candidate proposal with one of these five explicit states.
    """

    ACCEPTED_CANDIDATE = "ACCEPTED_CANDIDATE"
    """Sufficient evidence, valid data, within training distribution, calibrated probability
    >= frozen threshold, and positive estimated net expectancy."""

    NO_TRADE = "NO_TRADE"
    """Valid proposal and features, but calibrated probability is below the frozen threshold
    or estimated net expectancy is non-positive."""

    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    """Valid features within distribution, but calibration bin has low sample support (< N_min)
    or high epistemic uncertainty; abstention prevents false precision."""

    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    """Feature values exceed training distribution support domain (Out-of-Distribution / OOD);
    model refuses to extrapolate."""

    DATA_REJECTED = "DATA_REJECTED"
    """Missing features, unapproved feature names, non-finite values (NaN / Inf), stale timestamps,
    or invalid proposal schema."""


class CalibrationBin(BaseModel):
    """Statistics for an individual probability calibration bin in a reliability diagram."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bin_index: int = Field(..., ge=0, description="0-indexed bin rank")
    bin_lower: float = Field(..., ge=0.0, le=1.0, description="Inclusive lower probability bound")
    bin_upper: float = Field(..., ge=0.0, le=1.0, description="Upper probability bound")
    sample_count: int = Field(..., ge=0, description="Total labeled samples in this bin (N_b)")
    positive_count: int = Field(..., ge=0, description="Observed positive trades (k_b)")
    empirical_probability: float = Field(
        ..., ge=0.0, le=1.0, description="Observed historical win frequency (k_b / N_b)"
    )
    mean_predicted_probability: float = Field(
        ..., ge=0.0, le=1.0, description="Mean forecast probability in this bin (p_bar_b)"
    )
    avg_net_win: Decimal = Field(
        default=Decimal("0.00"), description="Average net P&L of winning trades in INR"
    )
    avg_net_loss: Decimal = Field(
        default=Decimal("0.00"), description="Average net P&L of losing trades in INR (negative)"
    )
    max_loss: Decimal = Field(
        default=Decimal("0.00"), description="Worst single trade loss in INR"
    )
    cvar_95: Decimal = Field(
        default=Decimal("0.00"), description="95% Conditional Value at Risk in INR (worst 5% mean)"
    )
    has_sufficient_support: bool = Field(
        default=False, description="True if sample_count >= min_bin_sample_support"
    )


class BrierDecomposition(BaseModel):
    """Murphy (1973) three-component decomposition of the Brier Score.

    Decomposition identity:
        BS = Reliability - Resolution + Uncertainty

    Scientific disclosure:
    Brier score combines calibration (reliability), discrimination (resolution), and uncertainty.
    A model with high discrimination power can achieve an artificially low (good) Brier score
    even when poorly calibrated. Thus, Brier score is NOT a pure calibration measure.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    reliability: float = Field(
        ..., ge=0.0, description="Calibration error component (weighted squared difference)"
    )
    resolution: float = Field(
        ..., ge=0.0, description="Discrimination component (sorting power against base rate)"
    )
    uncertainty: float = Field(
        ..., ge=0.0, description="Inherent problem variance component: p_bar * (1 - p_bar)"
    )
    decomposition_sum: float = Field(
        ..., description="Reliability - Resolution + Uncertainty"
    )


class ReliabilityDiagramData(BaseModel):
    """Reliability diagram evaluation data and proper scoring metrics on a partition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(..., min_length=3, max_length=100)
    partition_name: str = Field(..., min_length=1, max_length=50)
    bins: list[CalibrationBin] = Field(..., min_length=1)
    brier_score: float = Field(..., ge=0.0, le=1.0, description="Overall sample-level Brier Score")
    brier_decomposition: BrierDecomposition
    expected_calibration_error: float = Field(
        ..., ge=0.0, le=1.0, description="Expected Calibration Error (ECE)"
    )
    maximum_calibration_error: float = Field(
        ..., ge=0.0, le=1.0, description="Maximum Calibration Error (MCE)"
    )
    log_loss: float = Field(..., ge=0.0, description="Clipped logarithmic cross-entropy loss")
    total_samples: int = Field(..., ge=1)
    base_rate: float = Field(..., ge=0.0, le=1.0, description="Empirical base win rate (y_bar)")
    scientific_note: str = Field(
        default=(
            "Brier score decomposes into reliability (calibration error), resolution "
            "(discrimination power), and uncertainty (inherent variance): BS = Reliability - "
            "Resolution + Uncertainty. Brier score is not a pure calibration metric because "
            "high resolution can mask poor calibration. Reliability diagrams and ECE are "
            "mandatory alongside Brier score."
        )
    )


class DecisionDiagnostics(BaseModel):
    """Comprehensive diagnostic telemetry attached to every selective decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    predicted_probability: float = Field(..., ge=0.0, le=1.0)
    calibrated_probability: float = Field(..., ge=0.0, le=1.0)
    bin_index: int | None = Field(default=None)
    bin_sample_support: int = Field(default=0, ge=0)
    bin_observed_frequency: float | None = Field(default=None, ge=0.0, le=1.0)
    coverage_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    sample_support_warning: bool = Field(default=False)
    sample_support_message: str | None = Field(default=None)
    ood_warning: bool = Field(default=False)
    ood_message: str | None = Field(default=None)
    ood_outlier_features: list[str] = Field(default_factory=list)
    estimated_net_expectancy: Decimal = Field(default=Decimal("0.00"))
    expectancy_formula: str = Field(
        default=(
            "E[Net PnL] = p_bin * avg_net_win + (1 - p_bin) * avg_net_loss (in INR). "
            "Approach A labels already deduct statutory fees and slippage; costs are NOT "
            "subtracted a second time."
        )
    )
    downside_max_loss: Decimal = Field(default=Decimal("0.00"))
    downside_cvar_95: Decimal = Field(default=Decimal("0.00"))
    ambiguity_flags: list[str] = Field(default_factory=list)
    data_quality_flags: list[str] = Field(default_factory=list)
    notes: str = Field(default="")


class SelectiveDecision(BaseModel):
    """Immutable selective decision candidate record emitted by the decision engine.

    SEC-06 & SEC-19: A model decision alone NEVER directly authorizes a portfolio entry.
    Portfolio authorization, capital limits, risk sizing, and order placement remain
    independent responsibilities.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str = Field(..., min_length=5, max_length=100)
    decision_state: DecisionState = Field(...)
    proposal_id: str = Field(..., min_length=1, max_length=100)
    symbol: str = Field(..., min_length=1, max_length=20)
    timestamp: datetime = Field(..., description="Decision timestamp in UTC")
    model_id: str = Field(..., min_length=3, max_length=100)
    policy_id: str = Field(default="DECISION-POLICY-V1", max_length=50)
    diagnostics: DecisionDiagnostics = Field(...)
    is_portfolio_entry_authorized: bool = Field(
        default=False,
        description=(
            "A model decision alone never authorizes portfolio entry. Downstream risk "
            "authorization and execution engines must independently authorize orders."
        ),
    )
    created_at: datetime = Field(...)

    @field_validator("timestamp", "created_at", mode="before")
    @classmethod
    def validate_utc(cls, v: Any) -> datetime:
        return normalize_to_utc(v)


class FrozenDecisionPolicy(BaseModel):
    """Immutable, cryptographically hashed decision policy contract (DECISION-POLICY-V1).

    SEC-06, SEC-19 & SEC-23: Thresholds, calibration bins, and OOD bounds must be tuned strictly
    on development/calibration data and frozen. Tamper-evident SHA-256 hash verifies integrity.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str = Field(default="DECISION-POLICY-V1", max_length=50)
    model_id: str = Field(..., min_length=3, max_length=100)
    decision_threshold: float = Field(..., ge=0.0, le=1.0)
    min_bin_sample_support: int = Field(default=10, ge=1)
    min_expectancy: Decimal = Field(default=Decimal("0.00"))
    ood_bounds: dict[str, list[float]] = Field(
        ..., description="Feature min/max domain bounds fitted on TRAIN: {feat: [min, max]}"
    )
    calibration_bins: list[CalibrationBin] = Field(..., min_length=1)
    coverage_rate: float = Field(..., ge=0.0, le=1.0)
    frozen_at: datetime = Field(...)
    policy_hash: str = Field(..., description="SHA-256 hash of frozen policy parameters")

    @field_validator("frozen_at", mode="before")
    @classmethod
    def validate_utc(cls, v: Any) -> datetime:
        return normalize_to_utc(v)

    def calculate_policy_hash(self) -> str:
        """Calculate deterministic SHA-256 hash of this policy excluding policy_hash."""
        data_dict = self.model_dump(mode="json")
        data_dict.pop("policy_hash", None)
        canonical_json = json.dumps(data_dict, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
