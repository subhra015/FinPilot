"""Unit tests for MLSelectionPipeline (Layer 9).

Verifies:
- Training-only fit for preprocessing (imputers and scalers).
- Schema validation fail-closed on missing, unapproved, NaN, or Inf features.
- Probability calibration and decision threshold tuning.
- Proposal authorization API contract.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from finpilot.ml.models import CalibrationMethod, ModelFamily
from finpilot.ml.pipeline import MLSelectionPipeline, SchemaMismatchError
from finpilot.schemas.trade_policy import TradeProposal

IST = ZoneInfo("Asia/Kolkata")
FEATURE_NAMES = (
    "f_ret_5m",
    "f_rsi_14",
    "f_atr_14",
    "f_vol_ratio_5d",
    "f_dist_vwap",
)


@pytest.fixture
def sample_pipeline_data() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate synthetic deterministic feature matrices and labels for testing."""
    rng = np.random.RandomState(42)
    n_train = 100
    n_cal = 40

    # Train data: 5 features
    X_train = rng.randn(n_train, 5) * 2.0 + 10.0
    logit_train = 0.8 * X_train[:, 0] - 0.5 * X_train[:, 1]
    y_train = (logit_train > np.median(logit_train)).astype(int)

    # Cal data
    X_cal = rng.randn(n_cal, 5) * 2.0 + 10.0
    logit_cal = 0.8 * X_cal[:, 0] - 0.5 * X_cal[:, 1]
    y_cal = (logit_cal > np.median(logit_cal)).astype(int)

    return X_train, y_train, X_cal, y_cal


def test_pipeline_training_only_preprocessing_fit(
    sample_pipeline_data: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
) -> None:
    """Verify imputer and scaler fit ONLY on training data and never update during inference."""
    X_train, y_train, X_cal, y_cal = sample_pipeline_data

    # Introduce a missing NaN value in training data
    X_train_missing = X_train.copy()
    X_train_missing[0, 0] = np.nan

    pipeline = MLSelectionPipeline(
        model_id="MODEL-LOGREG-TEST",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_names=list(FEATURE_NAMES),
        base_estimator=LogisticRegression(random_state=42),
        calibration_method=CalibrationMethod.SIGMOID,
        decision_threshold=0.55,
    )

    pipeline.fit(X_train_missing, y_train, X_cal=X_cal, y_cal=y_cal)

    assert pipeline.scaler is not None
    assert pipeline.imputer is not None

    learned_mean = np.copy(pipeline.scaler.mean_)
    learned_imputer_stats = np.copy(pipeline.imputer.statistics_)

    # Inference on new unseen data with different mean
    X_unseen = np.ones((10, 5)) * 1000.0
    probs = pipeline.predict_proba_batch(X_unseen)

    assert len(probs) == 10
    # Preprocessor parameters must remain completely unchanged
    np.testing.assert_array_equal(pipeline.scaler.mean_, learned_mean)
    np.testing.assert_array_equal(pipeline.imputer.statistics_, learned_imputer_stats)


def test_pipeline_schema_mismatch_missing_feature(
    sample_pipeline_data: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
) -> None:
    """Verify predict_dict raises SchemaMismatchError when required features are missing."""
    X_train, y_train, X_cal, y_cal = sample_pipeline_data

    pipeline = MLSelectionPipeline(
        model_id="MODEL-LOGREG-TEST",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_names=list(FEATURE_NAMES),
        base_estimator=LogisticRegression(random_state=42),
    )
    pipeline.fit(X_train, y_train, X_cal=X_cal, y_cal=y_cal)

    incomplete_features = {
        "f_ret_5m": 0.002,
        "f_rsi_14": 55.4,
        "f_atr_14": 3.2,
        "f_vol_ratio_5d": 1.4,
    }

    with pytest.raises(SchemaMismatchError) as exc_info:
        pipeline.predict_dict(incomplete_features)
    assert "Missing required features" in str(exc_info.value)
    assert "f_dist_vwap" in str(exc_info.value)


def test_pipeline_schema_mismatch_unapproved_extra_feature(
    sample_pipeline_data: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
) -> None:
    """Verify predict_dict raises SchemaMismatchError when unexpected features are injected."""
    X_train, y_train, X_cal, y_cal = sample_pipeline_data

    pipeline = MLSelectionPipeline(
        model_id="MODEL-LOGREG-TEST",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_names=list(FEATURE_NAMES),
        base_estimator=LogisticRegression(random_state=42),
    )
    pipeline.fit(X_train, y_train, X_cal=X_cal, y_cal=y_cal)

    extra_features = {
        "f_ret_5m": 0.002,
        "f_rsi_14": 55.4,
        "f_atr_14": 3.2,
        "f_vol_ratio_5d": 1.4,
        "f_dist_vwap": 0.001,
        "future_leakage_feature": 123.45,
    }

    with pytest.raises(SchemaMismatchError) as exc_info:
        pipeline.predict_dict(extra_features)
    assert "Unexpected features" in str(exc_info.value)
    assert "future_leakage_feature" in str(exc_info.value)


def test_pipeline_schema_mismatch_nan_and_inf_at_inference(
    sample_pipeline_data: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
) -> None:
    """Verify predict_dict raises SchemaMismatchError on NaN or infinite values at inference."""
    X_train, y_train, X_cal, y_cal = sample_pipeline_data

    pipeline = MLSelectionPipeline(
        model_id="MODEL-LOGREG-TEST",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_names=list(FEATURE_NAMES),
        base_estimator=LogisticRegression(random_state=42),
    )
    pipeline.fit(X_train, y_train, X_cal=X_cal, y_cal=y_cal)

    nan_features = {
        "f_ret_5m": float("nan"),
        "f_rsi_14": 55.4,
        "f_atr_14": 3.2,
        "f_vol_ratio_5d": 1.4,
        "f_dist_vwap": 0.001,
    }

    with pytest.raises(SchemaMismatchError) as exc_info:
        pipeline.predict_dict(nan_features)
    assert "Non-finite feature value" in str(exc_info.value)

    inf_features = {
        "f_ret_5m": float("inf"),
        "f_rsi_14": 55.4,
        "f_atr_14": 3.2,
        "f_vol_ratio_5d": 1.4,
        "f_dist_vwap": 0.001,
    }

    with pytest.raises(SchemaMismatchError) as exc_info:
        pipeline.predict_dict(inf_features)
    assert "Non-finite feature value" in str(exc_info.value)


def test_pipeline_proposal_authorization(
    sample_pipeline_data: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
) -> None:
    """Verify should_authorize_proposal respects decision threshold."""
    X_train, y_train, X_cal, y_cal = sample_pipeline_data

    pipeline = MLSelectionPipeline(
        model_id="MODEL-LOGREG-TEST",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_names=list(FEATURE_NAMES),
        base_estimator=LogisticRegression(random_state=42),
        decision_threshold=0.60,
    )
    pipeline.fit(X_train, y_train, X_cal=X_cal, y_cal=y_cal)

    proposal = TradeProposal(
        proposal_id="PROP-TEST-001",
        instrument_id=1,
        symbol="RELIANCE",
        decision_timestamp=datetime(2026, 1, 16, 10, 0, tzinfo=IST),
        earliest_entry_timestamp=datetime(2026, 1, 16, 10, 5, tzinfo=IST),
        entry_price=Decimal("2500.00"),
        stop_loss=Decimal("2480.00"),
        target_price=Decimal("2540.00"),
        quantity=10,
        policy_version="TP-V1",
    )

    valid_features = {
        "f_ret_5m": 0.05,
        "f_rsi_14": 65.0,
        "f_atr_14": 15.0,
        "f_vol_ratio_5d": 2.5,
        "f_dist_vwap": 0.01,
    }

    authorized, proba = pipeline.should_authorize_proposal(proposal, valid_features)
    assert isinstance(authorized, bool)
    assert 0.0 <= proba <= 1.0
    assert authorized == (proba >= 0.60)
