"""Unit tests for ModelRegistry and artifact integrity security (Layer 9).

Verifies:
- SEC-06, SEC-18, SEC-23: Safe model loading.
- Rejection of path traversal attempts and untrusted filenames.
- SHA-256 cryptographic tamper detection on modified artifacts.
- Round-trip save and load parity for trusted models.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from finpilot.ml.models import (
    CalibrationMethod,
    ClassificationMetrics,
    ModelArtifactMetadata,
    ModelFamily,
)
from finpilot.ml.pipeline import MLSelectionPipeline
from finpilot.ml.registry import ModelRegistry, UntrustedArtifactError

FEATURE_NAMES = ("f_ret_5m", "f_rsi_14", "f_atr_14", "f_vol_ratio_5d", "f_dist_vwap")
UTC = ZoneInfo("UTC")


def make_metadata(model_id: str, threshold: float = 0.52) -> ModelArtifactMetadata:
    """Helper creating valid ModelArtifactMetadata."""
    return ModelArtifactMetadata(
        model_id=model_id,
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        description="Test logistic regression model artifact",
        feature_schema_version="FS-V1",
        feature_names=list(FEATURE_NAMES),
        training_start_time=datetime(2026, 1, 1, 9, 15, tzinfo=UTC),
        training_end_time=datetime(2026, 1, 15, 15, 30, tzinfo=UTC),
        split_manifest_id="SPLIT-TP-V1-TEST",
        hyperparameters={"C": 1.0, "penalty": "l2"},
        decision_threshold=threshold,
        calibration_method=CalibrationMethod.SIGMOID,
        validation_metrics=ClassificationMetrics(
            accuracy=0.60,
            roc_auc=0.62,
            pr_auc=0.58,
            brier_score=0.23,
            log_loss=0.65,
            positive_rate=0.45,
            sample_count=100,
        ),
        code_commit="HEAD",
        dependencies={"python": "3.13.15", "scikit-learn": "1.9.1"},
        artifact_checksum="",
        created_at=datetime(2026, 1, 16, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def fitted_pipeline() -> MLSelectionPipeline:
    """Return a simple fitted and calibrated pipeline."""
    rng = np.random.RandomState(42)
    X = rng.randn(50, 5)
    y = (X[:, 0] > 0).astype(int)

    pipeline = MLSelectionPipeline(
        model_id="MODEL-LOGREG-REGISTRY-TEST",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_names=list(FEATURE_NAMES),
        base_estimator=LogisticRegression(random_state=42),
        calibration_method=CalibrationMethod.SIGMOID,
        decision_threshold=0.52,
    )
    pipeline.fit(X, y, X_cal=X, y_cal=y)
    return pipeline


def test_registry_save_and_safe_load(
    tmp_path: Path, fitted_pipeline: MLSelectionPipeline
) -> None:
    """Verify clean save and cryptographic reload of trusted model artifact."""
    registry = ModelRegistry(registry_dir=tmp_path)
    metadata = make_metadata("MODEL-LOGREG-REGISTRY-TEST", 0.52)

    art_path, meta_path = registry.save_model(
        pipeline=fitted_pipeline,
        metadata=metadata,
    )

    assert art_path.exists()
    assert meta_path.exists()

    # Reload model from registry by model_id
    loaded_pipeline, loaded_metadata = registry.load_model("MODEL-LOGREG-REGISTRY-TEST")

    assert loaded_pipeline.model_id == fitted_pipeline.model_id
    assert loaded_pipeline.decision_threshold == 0.52
    assert loaded_metadata.artifact_checksum != ""

    # Verify predictions match exactly
    X_test = np.ones((5, 5))
    orig_preds = fitted_pipeline.predict_proba_batch(X_test)
    loaded_preds = loaded_pipeline.predict_proba_batch(X_test)
    np.testing.assert_allclose(orig_preds, loaded_preds, rtol=1e-5)


def test_registry_tamper_detection_raises_untrusted_artifact(
    tmp_path: Path, fitted_pipeline: MLSelectionPipeline
) -> None:
    """Verify tampering with a single byte in the artifact file fails SHA-256 integrity check."""
    registry = ModelRegistry(registry_dir=tmp_path)
    metadata = make_metadata("MODEL-TAMPER-TEST", 0.50)

    art_path, _ = registry.save_model(
        pipeline=fitted_pipeline,
        metadata=metadata,
    )

    # Corrupt the artifact file by appending or altering bytes
    with open(art_path, "ab") as f:
        f.write(b"CORRUPTED_BYTES_INJECTED")

    # Attempting to load must raise UntrustedArtifactError before unpickling
    with pytest.raises(UntrustedArtifactError) as exc_info:
        registry.load_model("MODEL-TAMPER-TEST")

    assert "Integrity check failed" in str(exc_info.value)
    assert "computed checksum" in str(exc_info.value)


def test_registry_path_traversal_rejection(tmp_path: Path) -> None:
    """Verify attempting to access models outside the trusted registry directory is blocked."""
    registry = ModelRegistry(registry_dir=tmp_path)

    traversal_names = [
        "../evil_model",
        "../../etc/passwd",
        r"..\..\windows\system32\calc",
        "sub/../../escape",
        "nested/path/model",
    ]

    for bad_name in traversal_names:
        with pytest.raises(UntrustedArtifactError) as exc_info:
            registry.load_model(bad_name)
        assert (
            "Invalid or uncontained" in str(exc_info.value)
            or "Path traversal detected" in str(exc_info.value)
        )


def test_registry_missing_files_fail_closed(tmp_path: Path) -> None:
    """Verify trying to load a non-existent artifact fails closed with UntrustedArtifactError."""
    registry = ModelRegistry(registry_dir=tmp_path)

    with pytest.raises(UntrustedArtifactError) as exc_info:
        registry.load_model("MODEL-DOES-NOT-EXIST")

    assert "does not exist" in str(exc_info.value)


def test_registry_corrupted_metadata_fail_closed(
    tmp_path: Path, fitted_pipeline: MLSelectionPipeline
) -> None:
    """Verify invalid or unparseable metadata json raises UntrustedArtifactError."""
    registry = ModelRegistry(registry_dir=tmp_path)
    metadata = make_metadata("MODEL-BAD-META", 0.50)

    _, meta_path = registry.save_model(
        pipeline=fitted_pipeline,
        metadata=metadata,
    )

    # Corrupt the metadata file with garbage JSON
    with open(meta_path, "w", encoding="utf-8") as f:
        f.write("{ INVALID JSON CONTENT }")

    with pytest.raises(UntrustedArtifactError) as exc_info:
        registry.load_model("MODEL-BAD-META")

    assert "Failed to parse metadata" in str(exc_info.value)
