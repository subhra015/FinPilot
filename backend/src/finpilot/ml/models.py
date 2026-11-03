"""Domain models and schemas for ML baseline models and selection layer (Layer 9).

Governed by:
- PROJECT_SPEC.md §4, §5, §7, §9
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 9 Gate: Baseline ML model training, training-only fit, reproducible seeds,
  immutable artifact metadata, safe loading, and selection layer evaluation.
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


class ModelFamily(StrEnum):
    """Permitted initial ML model families (Layer 9)."""

    LOGISTIC_REGRESSION = "LOGISTIC_REGRESSION"
    LIGHTGBM = "LIGHTGBM"


class CalibrationMethod(StrEnum):
    """Probability calibration method."""

    SIGMOID = "SIGMOID"
    ISOTONIC = "ISOTONIC"
    NONE = "NONE"


class ClassificationMetrics(BaseModel):
    """Validation classification and calibration performance metrics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    accuracy: float = Field(..., ge=0.0, le=1.0)
    roc_auc: float = Field(..., ge=0.0, le=1.0)
    pr_auc: float = Field(..., ge=0.0, le=1.0)
    brier_score: float = Field(..., ge=0.0, le=1.0)
    log_loss: float = Field(..., ge=0.0)
    positive_rate: float = Field(..., ge=0.0, le=1.0)
    sample_count: int = Field(..., ge=1)


class SelectionEvaluationMetrics(BaseModel):
    """Economic portfolio metrics of the ML model acting as an authorization filter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_name: str = Field(default="STRAT-SIMPLE-V1")
    model_id: str | None = Field(default=None)
    total_proposals_evaluated: int = Field(..., ge=0)
    proposals_authorized: int = Field(..., ge=0)
    proposals_vetoed: int = Field(..., ge=0)
    filter_rate_pct: float = Field(..., ge=0.0, le=100.0)
    total_trades_filled: int = Field(..., ge=0)
    winning_trades: int = Field(..., ge=0)
    win_rate: float = Field(..., ge=0.0, le=1.0)
    gross_pnl: Decimal = Field(...)
    fees: Decimal = Field(..., ge=Decimal("0.00"))
    net_pnl: Decimal = Field(...)
    profit_factor: float = Field(..., ge=0.0)
    max_drawdown_amount: Decimal = Field(..., ge=Decimal("0.00"))
    max_drawdown_pct: float = Field(..., ge=0.0)
    ledger_reconciled: bool = Field(...)
    accounting_discrepancy: Decimal = Field(..., le=Decimal("0.01"))


class ModelArtifactMetadata(BaseModel):
    """Comprehensive, immutable metadata attached to every trained model artifact.

    SEC-06 & SEC-23: Contains exact feature schema, training date bounds, split ID,
    code commit, dependencies, and cryptographic artifact checksum.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(..., min_length=3, max_length=100)
    model_family: ModelFamily = Field(...)
    description: str = Field(..., min_length=5, max_length=500)
    feature_schema_version: str = Field(default="FS-V1", max_length=20)
    feature_names: list[str] = Field(..., min_length=1)
    training_start_time: datetime = Field(...)
    training_end_time: datetime = Field(...)
    split_manifest_id: str = Field(..., min_length=5, max_length=100)
    hyperparameters: dict[str, Any] = Field(...)
    calibration_method: CalibrationMethod = Field(default=CalibrationMethod.NONE)
    decision_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    validation_metrics: ClassificationMetrics = Field(...)
    code_commit: str = Field(..., min_length=4, max_length=100)
    dependencies: dict[str, str] = Field(..., description="Exact versions of core libraries")
    artifact_checksum: str = Field(..., description="SHA-256 digest of serialized model pipeline")
    created_at: datetime = Field(...)

    @field_validator("training_start_time", "training_end_time", "created_at", mode="before")
    @classmethod
    def validate_utc(cls, v: Any) -> datetime:
        return normalize_to_utc(v)

    def calculate_metadata_hash(self) -> str:
        """Calculate deterministic SHA-256 hash of this metadata model."""
        meta_dict = self.model_dump(mode="json")
        canonical_json = json.dumps(meta_dict, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class ModelSelectionComparison(BaseModel):
    """Direct economic comparison between baselines and candidate ML selection filters."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evaluation_period: str = Field(..., description="Date range or partition identifier")
    split_manifest_id: str = Field(...)
    no_trade_result: SelectionEvaluationMetrics = Field(...)
    simple_baseline_result: SelectionEvaluationMetrics = Field(...)
    ml_candidate_results: dict[str, SelectionEvaluationMetrics] = Field(...)
    model_contributions: dict[str, dict[str, Any]] = Field(
        ...,
        description="Economic deltas: fee savings, net P&L difference, churn reduction",
    )
    recommended_model_id: str | None = Field(default=None)
    recommendation_rationale: str = Field(..., max_length=1000)
