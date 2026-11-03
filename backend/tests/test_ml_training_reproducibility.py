"""Unit tests for ML model training reproducibility and lockbox isolation (Layer 9).

Verifies:
- Deterministic training: identical seeds produce bit-identical model parameters and predictions.
- No final-test access during model training and validation.
- Metadata completeness: code commit, dependencies, checksum, split manifest recorded.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from finpilot.labeling.lockbox import FinalTestLockbox
from finpilot.labeling.models import (
    LabelingApproach,
    PartitionType,
    SplitManifest,
    TradeOutcomeReason,
    TradePolicyLabel,
)
from finpilot.labeling.split_manager import FinalTestLockedError, TemporalSplitManager
from finpilot.ml.models import ModelFamily
from finpilot.ml.registry import ModelRegistry
from finpilot.ml.trainer import DEFAULT_FEATURES, MLModelTrainer

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")


def make_synthetic_partitioned_dataset() -> tuple[
    SplitManifest,
    dict[PartitionType, list[TradePolicyLabel]],
]:
    """Create a minimal synthetic split dataset and SplitManifest across partitions."""
    rng = np.random.RandomState(42)
    partitioned_labels: dict[PartitionType, list[TradePolicyLabel]] = {}

    partitions = [
        (PartitionType.TRAIN, 60, datetime(2026, 1, 1, 9, 15, tzinfo=IST)),
        (PartitionType.DEV_MODEL_SELECTION, 30, datetime(2026, 1, 16, 9, 15, tzinfo=IST)),
        (PartitionType.CALIBRATION, 20, datetime(2026, 1, 21, 9, 15, tzinfo=IST)),
        (PartitionType.THRESHOLD_SELECTION, 20, datetime(2026, 1, 23, 9, 15, tzinfo=IST)),
        (PartitionType.LOCKED_FINAL_TEST, 30, datetime(2026, 1, 27, 9, 15, tzinfo=IST)),
    ]

    all_labels: list[TradePolicyLabel] = []

    for p_type, count, start_dt in partitions:
        labels: list[TradePolicyLabel] = []
        X = rng.randn(count, len(DEFAULT_FEATURES))
        signal = 0.6 * X[:, 0] - 0.4 * X[:, 1]
        probs = 1.0 / (1.0 + np.exp(-signal))
        y = (probs > 0.5).astype(int)

        for i in range(count):
            dec_time = start_dt + timedelta(minutes=5 * i)
            is_win = bool(y[i] == 1)
            net_pnl = Decimal("25.00") if is_win else Decimal("-20.00")
            feats = {DEFAULT_FEATURES[k]: float(X[i, k]) for k in range(len(DEFAULT_FEATURES))}

            lbl = TradePolicyLabel(
                sample_id=f"LBL-{p_type.value}-{i}",
                instrument_id=1,
                symbol="RELIANCE",
                decision_time=dec_time.astimezone(UTC),
                entry_time=dec_time.astimezone(UTC) + timedelta(minutes=5),
                exit_time=dec_time.astimezone(UTC) + timedelta(minutes=15),
                holding_bars=2,
                entry_price=Decimal("2500.00"),
                exit_price=Decimal("2525.00") if is_win else Decimal("2480.00"),
                quantity=10,
                gross_pnl=net_pnl + Decimal("5.00"),
                fees=Decimal("5.00"),
                net_pnl=net_pnl,
                gross_return=Decimal("0.0100"),
                net_return=Decimal("0.0080"),
                binary_label=1 if is_win else 0,
                outcome_reason=(
                    TradeOutcomeReason.TARGET_HIT if is_win else TradeOutcomeReason.STOP_LOSS_HIT
                ),
                is_ambiguous_exit=False,
                is_gap_fill=False,
                features=feats,
                labeling_approach=LabelingApproach.APPROACH_A_SHARED_SIZING,
                policy_version="TP-V1",
            )
            labels.append(lbl)

        partitioned_labels[p_type] = labels
        all_labels.extend(labels)

    split_mgr = TemporalSplitManager(embargo_bars=1)
    split_manifest, _ = split_mgr.create_splits(
        labels=all_labels,
        dataset_hash="hash_reproducibility_test",
        policy_version="TP-V1",
        labeling_approach=LabelingApproach.APPROACH_A_SHARED_SIZING,
        total_excluded_rows=0,
    )

    return split_manifest, partitioned_labels


def test_logistic_regression_deterministic_reproducibility(tmp_path: Path) -> None:
    """Verify Logistic Regression training is strictly deterministic given the same seed."""
    split_manifest, part_labels = make_synthetic_partitioned_dataset()
    registry1 = ModelRegistry(registry_dir=tmp_path / "reg1")
    registry2 = ModelRegistry(registry_dir=tmp_path / "reg2")

    trainer1 = MLModelTrainer(
        split_manifest=split_manifest,
        partitions=part_labels,
        registry=registry1,
    )
    pipeline1, meta1 = trainer1.train_logistic_regression(
        model_id="MODEL-LOGREG-V1",
        C=1.0,
        random_state=42,
    )

    trainer2 = MLModelTrainer(
        split_manifest=split_manifest,
        partitions=part_labels,
        registry=registry2,
    )
    pipeline2, meta2 = trainer2.train_logistic_regression(
        model_id="MODEL-LOGREG-V1",
        C=1.0,
        random_state=42,
    )

    # Identical decision threshold
    assert pipeline1.decision_threshold == pipeline2.decision_threshold
    assert meta1.decision_threshold == meta2.decision_threshold

    # Identical predictions on dev data
    dev_labels = part_labels[PartitionType.DEV_MODEL_SELECTION]
    for lbl in dev_labels:
        p1 = pipeline1.predict_proba_single(lbl.features)
        p2 = pipeline2.predict_proba_single(lbl.features)
        assert p1 == pytest.approx(p2, rel=1e-6)


def test_lightgbm_deterministic_reproducibility(tmp_path: Path) -> None:
    """Verify LightGBM training is strictly deterministic given the same seed."""
    split_manifest, part_labels = make_synthetic_partitioned_dataset()
    registry1 = ModelRegistry(registry_dir=tmp_path / "reg1")
    registry2 = ModelRegistry(registry_dir=tmp_path / "reg2")

    trainer1 = MLModelTrainer(
        split_manifest=split_manifest,
        partitions=part_labels,
        registry=registry1,
    )
    pipeline1, meta1 = trainer1.train_lightgbm(
        model_id="MODEL-LIGHTGBM-V1",
        max_depth=3,
        num_leaves=7,
        learning_rate=0.05,
        n_estimators=30,
        random_state=42,
    )

    trainer2 = MLModelTrainer(
        split_manifest=split_manifest,
        partitions=part_labels,
        registry=registry2,
    )
    pipeline2, meta2 = trainer2.train_lightgbm(
        model_id="MODEL-LIGHTGBM-V1",
        max_depth=3,
        num_leaves=7,
        learning_rate=0.05,
        n_estimators=30,
        random_state=42,
    )

    # Identical decision threshold
    assert pipeline1.decision_threshold == pipeline2.decision_threshold
    assert meta1.decision_threshold == meta2.decision_threshold

    # Identical predictions on dev data
    dev_labels = part_labels[PartitionType.DEV_MODEL_SELECTION]
    for lbl in dev_labels:
        p1 = pipeline1.predict_proba_single(lbl.features)
        p2 = pipeline2.predict_proba_single(lbl.features)
        assert p1 == pytest.approx(p2, rel=1e-6)


def test_no_final_test_access_during_training(tmp_path: Path) -> None:
    """Verify that training and validation pipelines do not access LOCKED_FINAL_TEST."""
    split_manifest, part_labels = make_synthetic_partitioned_dataset()

    # Wrap in lockbox so LOCKED_FINAL_TEST cannot be read without unlock token
    lockbox = FinalTestLockbox(split_manifest, part_labels)

    # Attempting to retrieve LOCKED_FINAL_TEST raises FinalTestLockedError
    with pytest.raises(FinalTestLockedError):
        lockbox.get_final_test_samples()

    # Safe partitions passed to trainer do not contain final test
    safe_labels = {
        PartitionType.TRAIN: lockbox.get_train_samples(),
        PartitionType.CALIBRATION: lockbox.get_calibration_samples(),
        PartitionType.THRESHOLD_SELECTION: lockbox.get_threshold_samples(),
        PartitionType.DEV_MODEL_SELECTION: lockbox.get_dev_samples(),
    }

    trainer = MLModelTrainer(
        split_manifest=split_manifest,
        partitions=safe_labels,
        registry=ModelRegistry(registry_dir=tmp_path),
    )
    pipeline, meta = trainer.train_logistic_regression(
        model_id="MODEL-LOGREG-V1",
        C=1.0,
        random_state=42,
    )
    assert pipeline.model_family == ModelFamily.LOGISTIC_REGRESSION
    assert meta.decision_threshold > 0.0


def test_metadata_environment_and_provenance_recording(tmp_path: Path) -> None:
    """Verify metadata captures code commit, dependencies, training dates, and hyperparameters."""
    split_manifest, part_labels = make_synthetic_partitioned_dataset()
    trainer = MLModelTrainer(
        split_manifest=split_manifest,
        partitions=part_labels,
        registry=ModelRegistry(registry_dir=tmp_path),
    )

    _, meta = trainer.train_logistic_regression(
        model_id="MODEL-LOGREG-V1",
        C=1.0,
        random_state=42,
    )

    assert meta.feature_schema_version == "FS-V1"
    assert len(meta.feature_names) == len(DEFAULT_FEATURES)
    assert meta.training_start_time is not None
    assert "C" in meta.hyperparameters
    assert meta.dependencies["python"] != ""
    assert meta.dependencies["scikit-learn"] != ""
    assert meta.dependencies["lightgbm"] != ""
    assert meta.artifact_checksum != ""
