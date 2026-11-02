"""Unit and leakage-prevention tests for deterministic feature transforms (Layer 5)."""

from __future__ import annotations

import pytest

from finpilot.features.transforms import DeterministicFeatureScaler
from finpilot.schemas.errors import DomainValidationError


def test_scaler_training_only_fit_and_transform() -> None:
    scaler = DeterministicFeatureScaler(feature_names=["feat_a", "feat_b"])
    train_records = [
        {"feat_a": 10.0, "feat_b": 100.0},
        {"feat_a": 20.0, "feat_b": 200.0},
        {"feat_a": 30.0, "feat_b": 300.0},
    ]

    scaler.fit(train_records)
    assert scaler.is_fitted is True
    assert scaler.fit_sample_count == 3
    assert scaler.fit_checksum is not None

    stats_a = scaler.stats["feat_a"]
    # Mean of [10, 20, 30] = 20.0, variance = ((100 + 0 + 100)/3) = 66.6666...
    assert stats_a.mean == pytest.approx(20.0)
    assert stats_a.std == pytest.approx((200.0 / 3.0) ** 0.5)

    # Transform train data
    transformed_train = scaler.transform(train_records)
    assert len(transformed_train) == 3
    # Middle record (20.0) should be 0.0 scaled
    assert transformed_train[1]["feat_a"] == pytest.approx(0.0)


def test_scaler_transform_does_not_mutate_fitted_parameters() -> None:
    """CRITICAL LEAKAGE TEST: Transforming test data must NOT change scaler parameters."""
    scaler = DeterministicFeatureScaler()
    train_data = [{"feat": 10.0}, {"feat": 20.0}, {"feat": 30.0}]
    scaler.fit(train_data)

    initial_mean = scaler.stats["feat"].mean
    initial_std = scaler.stats["feat"].std
    initial_checksum = scaler.fit_checksum

    # Transform massive unseen test data with totally different distribution
    test_data = [{"feat": 1000.0}, {"feat": 2000.0}, {"feat": 5000.0}]
    scaler.transform(test_data)

    # Assert scaler parameters remained completely unchanged
    assert scaler.stats["feat"].mean == initial_mean
    assert scaler.stats["feat"].std == initial_std
    assert scaler.fit_checksum == initial_checksum


def test_scaler_unfitted_transform_rejected() -> None:
    scaler = DeterministicFeatureScaler()
    with pytest.raises(DomainValidationError) as exc:
        scaler.transform([{"feat": 10.0}])
    assert "must be fitted" in str(exc.value)


def test_scaler_rejects_non_finite_values() -> None:
    scaler = DeterministicFeatureScaler()
    # NaN in fit
    with pytest.raises(DomainValidationError) as exc:
        scaler.fit([{"feat": float("nan")}])
    assert "Non-finite" in str(exc.value)

    # Inf in fit
    with pytest.raises(DomainValidationError) as exc2:
        scaler.fit([{"feat": float("inf")}])
    assert "Non-finite" in str(exc2.value)

    # Inf in transform
    scaler.fit([{"feat": 10.0}, {"feat": 20.0}])
    with pytest.raises(DomainValidationError) as exc3:
        scaler.transform([{"feat": float("-inf")}])
    assert "Non-finite" in str(exc3.value)


def test_scaler_constant_feature_zero_variance_guard() -> None:
    scaler = DeterministicFeatureScaler()
    # Constant value -> std = 0.0 -> guard sets std to 1.0
    scaler.fit([{"const": 5.0}, {"const": 5.0}, {"const": 5.0}])
    assert scaler.stats["const"].std == 1.0

    transformed = scaler.transform([{"const": 5.0}])
    # (5.0 - 5.0) / 1.0 = 0.0
    assert transformed[0]["const"] == pytest.approx(0.0)


def test_scaler_serialization_roundtrip_and_checksum_integrity() -> None:
    scaler = DeterministicFeatureScaler()
    scaler.fit([{"f1": 1.0, "f2": 10.0}, {"f1": 3.0, "f2": 30.0}])

    # Serialize
    state = scaler.to_dict()
    assert "fit_checksum" in state
    assert state["is_fitted"] is True

    # Deserialize
    restored = DeterministicFeatureScaler.from_dict(state)
    assert restored.is_fitted is True
    assert restored.fit_checksum == scaler.fit_checksum
    assert restored.stats["f1"].mean == scaler.stats["f1"].mean

    # Tampered checksum raises error
    state_tampered = dict(state)
    state_tampered["fit_checksum"] = "bad" * 16
    with pytest.raises(DomainValidationError) as exc:
        DeterministicFeatureScaler.from_dict(state_tampered)
    assert "Checksum mismatch" in str(exc.value)
