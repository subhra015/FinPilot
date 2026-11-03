"""FinPilot AI — Baseline ML Model Training & Selection Layer (Layer 9).

Governed by:
- PROJECT_SPEC.md §4, §5, §7, §9
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 9 Gate: Baseline ML training (Logistic Regression + LightGBM),
  training-only fit, calibration, safe model registry, and economic selection evaluation.
"""

from __future__ import annotations

from .evaluator import SelectionLayerEvaluator
from .models import (
    CalibrationMethod,
    ClassificationMetrics,
    ModelArtifactMetadata,
    ModelFamily,
    ModelSelectionComparison,
    SelectionEvaluationMetrics,
)
from .pipeline import MLSelectionPipeline, SchemaMismatchError
from .registry import DEFAULT_MODELS_DIR, ModelRegistry, UntrustedArtifactError
from .trainer import DEFAULT_FEATURES, MLModelTrainer

__all__ = [
    "CalibrationMethod",
    "ClassificationMetrics",
    "DEFAULT_FEATURES",
    "DEFAULT_MODELS_DIR",
    "MLModelTrainer",
    "MLSelectionPipeline",
    "ModelArtifactMetadata",
    "ModelFamily",
    "ModelRegistry",
    "ModelSelectionComparison",
    "SchemaMismatchError",
    "SelectionEvaluationMetrics",
    "SelectionLayerEvaluator",
    "UntrustedArtifactError",
]
