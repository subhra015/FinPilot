"""Tests for selective decision logic, abstention states, and diagnostics (Layer 10).

Governed by:
- PROJECT_SPEC.md §4, §5, §7, §9
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 10 Gate: 5-state selective decision logic, sample support and OOD abstention,
  expectancy estimation without double cost deduction, and candidate semantics.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from finpilot.decision.engine import SelectiveDecisionEngine
from finpilot.decision.models import (
    CalibrationBin,
    DecisionState,
    FrozenDecisionPolicy,
)
from finpilot.ml.models import CalibrationMethod, ModelFamily
from finpilot.ml.pipeline import MLSelectionPipeline
from finpilot.schemas.trade_policy import TradeProposal


@pytest.fixture
def trained_pipeline() -> MLSelectionPipeline:
    """Fixture providing a fitted, calibrated MLSelectionPipeline with realistic feature scales."""
    feature_names = ["ret_1", "sma_ratio_9_21", "rsi_14", "causal_rel_vol"]
    pipeline = MLSelectionPipeline(
        model_id="MODEL-FIXTURE-V1",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_names=feature_names,
        base_estimator=LogisticRegression(random_state=42),
        calibration_method=CalibrationMethod.SIGMOID,
        decision_threshold=0.50,
    )
    # Synthetic training data with realistic indicator scales
    base_X = np.array(
        [
            [-0.02, 0.98, 30.0, 0.8],  # low (class 0)
            [-0.01, 0.99, 40.0, 0.9],  # low (class 0)
            [0.00, 1.00, 50.0, 1.0],  # mid (class 0)
            [0.005, 1.01, 60.0, 1.2],  # high (class 1)
            [0.01, 1.02, 70.0, 1.8],  # high (class 1)
            [0.05, 1.08, 92.0, 4.0],  # extreme (class 1)
        ]
    )
    base_y = np.array([0, 0, 0, 1, 1, 1])

    X_train = np.repeat(base_X, 25, axis=0)
    y_train = np.repeat(base_y, 25)

    X_cal = np.repeat(base_X, 10, axis=0)
    y_cal = np.repeat(base_y, 10)

    pipeline.fit(X_train, y_train, X_cal=X_cal, y_cal=y_cal)
    return pipeline


@pytest.fixture
def frozen_policy() -> FrozenDecisionPolicy:
    """Fixture providing a frozen decision policy with calibrated bins and OOD bounds."""
    # 5 bins: [0.0, 0.2), [0.2, 0.4), [0.4, 0.6), [0.6, 0.8), [0.8, 1.0]
    bins = [
        CalibrationBin(
            bin_index=0,
            bin_lower=0.0,
            bin_upper=0.2,
            sample_count=20,
            positive_count=2,
            empirical_probability=0.10,
            mean_predicted_probability=0.10,
            avg_net_win=Decimal("350.00"),
            avg_net_loss=Decimal("-300.00"),
            max_loss=Decimal("-350.00"),
            cvar_95=Decimal("-350.00"),
            has_sufficient_support=True,
        ),
        CalibrationBin(
            bin_index=1,
            bin_lower=0.2,
            bin_upper=0.4,
            sample_count=25,
            positive_count=8,
            empirical_probability=0.32,
            mean_predicted_probability=0.30,
            avg_net_win=Decimal("400.00"),
            avg_net_loss=Decimal("-300.00"),
            max_loss=Decimal("-350.00"),
            cvar_95=Decimal("-350.00"),
            has_sufficient_support=True,
        ),
        CalibrationBin(
            bin_index=2,
            bin_lower=0.4,
            bin_upper=0.6,
            sample_count=30,
            positive_count=15,
            empirical_probability=0.50,
            mean_predicted_probability=0.50,
            avg_net_win=Decimal("450.00"),
            avg_net_loss=Decimal("-300.00"),
            max_loss=Decimal("-350.00"),
            cvar_95=Decimal("-350.00"),
            has_sufficient_support=True,
        ),
        CalibrationBin(
            bin_index=3,
            bin_lower=0.6,
            bin_upper=0.8,
            sample_count=25,
            positive_count=18,
            empirical_probability=0.72,
            mean_predicted_probability=0.70,
            avg_net_win=Decimal("500.00"),
            avg_net_loss=Decimal("-300.00"),
            max_loss=Decimal("-350.00"),
            cvar_95=Decimal("-350.00"),
            has_sufficient_support=True,
        ),
        CalibrationBin(
            bin_index=4,
            bin_lower=0.8,
            bin_upper=1.0,
            sample_count=5,  # Low support (< 10) to test abstention!
            positive_count=4,
            empirical_probability=0.80,
            mean_predicted_probability=0.85,
            avg_net_win=Decimal("600.00"),
            avg_net_loss=Decimal("-300.00"),
            max_loss=Decimal("-350.00"),
            cvar_95=Decimal("-350.00"),
            has_sufficient_support=False,
        ),
    ]

    ood_bounds = {
        "ret_1": [-0.10, 0.10],
        "sma_ratio_9_21": [0.80, 1.20],
        "rsi_14": [0.0, 100.0],
        "causal_rel_vol": [0.0, 10.0],
    }

    policy = FrozenDecisionPolicy(
        policy_id="DECISION-POLICY-V1",
        model_id="MODEL-FIXTURE-V1",
        decision_threshold=0.60,
        min_bin_sample_support=10,
        min_expectancy=Decimal("0.00"),
        ood_bounds=ood_bounds,
        calibration_bins=bins,
        coverage_rate=0.25,
        frozen_at=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
        policy_hash="mock_hash_for_test",
    )
    # Update with real hash
    return policy.model_copy(update={"policy_hash": policy.calculate_policy_hash()})


@pytest.fixture
def sample_proposal() -> TradeProposal:
    """Fixture providing a valid TP-V1 TradeProposal."""
    return TradeProposal(
        proposal_id="PROP-TEST-001",
        instrument_id=101,
        symbol="RELIANCE",
        decision_timestamp=datetime(2026, 1, 15, 5, 25, tzinfo=UTC),
        earliest_entry_timestamp=datetime(2026, 1, 15, 5, 30, tzinfo=UTC),
        entry_price=Decimal("2500.00"),
        stop_loss=Decimal("2475.00"),
        target_price=Decimal("2550.00"),
        quantity=12,
    )


def test_accepted_candidate_decision(
    trained_pipeline: MLSelectionPipeline,
    frozen_policy: FrozenDecisionPolicy,
    sample_proposal: TradeProposal,
) -> None:
    """Test ACCEPTED_CANDIDATE when probability >= threshold and positive expectancy."""
    engine = SelectiveDecisionEngine(pipeline=trained_pipeline, policy=frozen_policy)

    # Features designed to produce probability in bin 3 [0.6, 0.8)
    features = {
        "ret_1": 0.005,
        "sma_ratio_9_21": 1.01,
        "rsi_14": 60.0,
        "causal_rel_vol": 1.2,
    }

    decision = engine.evaluate_proposal(sample_proposal, features)

    # State verification
    assert decision.decision_state == DecisionState.ACCEPTED_CANDIDATE
    # Invariant: model score alone never authorizes
    assert decision.is_portfolio_entry_authorized is False
    assert decision.proposal_id == "PROP-TEST-001"
    assert decision.symbol == "RELIANCE"

    # Diagnostics verification
    diag = decision.diagnostics
    assert diag.predicted_probability >= 0.60
    assert diag.bin_index == 3
    assert diag.bin_sample_support == 25
    assert diag.bin_observed_frequency == 0.72
    assert diag.estimated_net_expectancy > Decimal("0.00")
    assert diag.sample_support_warning is False
    assert diag.ood_warning is False
    assert len(diag.data_quality_flags) == 0


def test_no_trade_decision_below_threshold(
    trained_pipeline: MLSelectionPipeline,
    frozen_policy: FrozenDecisionPolicy,
    sample_proposal: TradeProposal,
) -> None:
    """Test NO_TRADE when calibrated probability is below the frozen threshold."""
    engine = SelectiveDecisionEngine(pipeline=trained_pipeline, policy=frozen_policy)

    # Features designed to produce low probability (e.g. negative momentum)
    features = {
        "ret_1": -0.05,
        "sma_ratio_9_21": 0.95,
        "rsi_14": 25.0,
        "causal_rel_vol": 1.0,
    }

    decision = engine.evaluate_proposal(sample_proposal, features)

    assert decision.decision_state == DecisionState.NO_TRADE
    assert decision.is_portfolio_entry_authorized is False
    assert decision.diagnostics.predicted_probability < 0.60
    assert "no trade authorized" in decision.diagnostics.notes.lower()


def test_insufficient_evidence_abstention(
    trained_pipeline: MLSelectionPipeline,
    frozen_policy: FrozenDecisionPolicy,
    sample_proposal: TradeProposal,
) -> None:
    """Test INSUFFICIENT_EVIDENCE when prediction falls into a bin with sample_count < N_min."""
    engine = SelectiveDecisionEngine(pipeline=trained_pipeline, policy=frozen_policy)

    # Features yielding high prob (> 0.80), landing in Bin 4 (which has only 5 samples)
    features = {
        "ret_1": 0.09,
        "sma_ratio_9_21": 1.15,
        "rsi_14": 92.0,
        "causal_rel_vol": 3.0,
    }

    decision = engine.evaluate_proposal(sample_proposal, features)

    assert decision.decision_state == DecisionState.INSUFFICIENT_EVIDENCE
    assert decision.is_portfolio_entry_authorized is False
    assert decision.diagnostics.bin_index == 4
    assert decision.diagnostics.bin_sample_support == 5
    assert decision.diagnostics.sample_support_warning is True
    assert "below required support 10" in (decision.diagnostics.sample_support_message or "")


def test_out_of_scope_ood_abstention(
    trained_pipeline: MLSelectionPipeline,
    frozen_policy: FrozenDecisionPolicy,
    sample_proposal: TradeProposal,
) -> None:
    """Test OUT_OF_SCOPE when feature values violate training domain bounds."""
    engine = SelectiveDecisionEngine(pipeline=trained_pipeline, policy=frozen_policy)

    # causal_rel_vol = 50.0 exceeds upper bound 10.0
    features = {
        "ret_1": 0.02,
        "sma_ratio_9_21": 1.01,
        "rsi_14": 60.0,
        "causal_rel_vol": 50.0,
    }

    decision = engine.evaluate_proposal(sample_proposal, features)

    assert decision.decision_state == DecisionState.OUT_OF_SCOPE
    assert decision.is_portfolio_entry_authorized is False
    assert decision.diagnostics.ood_warning is True
    assert any("causal_rel_vol" in f for f in decision.diagnostics.ood_outlier_features)
    assert "refuses to extrapolate" in decision.diagnostics.notes


def test_data_rejected_missing_or_non_finite_features(
    trained_pipeline: MLSelectionPipeline,
    frozen_policy: FrozenDecisionPolicy,
    sample_proposal: TradeProposal,
) -> None:
    """Test DATA_REJECTED on missing features, unknown features, or NaN/Inf."""
    engine = SelectiveDecisionEngine(pipeline=trained_pipeline, policy=frozen_policy)

    # Case 1: Missing feature
    missing_features = {"ret_1": 0.01, "rsi_14": 50.0}
    dec_missing = engine.evaluate_proposal(sample_proposal, missing_features)
    assert dec_missing.decision_state == DecisionState.DATA_REJECTED
    flags = dec_missing.diagnostics.data_quality_flags
    assert any("Missing required features" in flag for flag in flags)

    # Case 2: Non-finite NaN value
    nan_features = {
        "ret_1": float("nan"),
        "sma_ratio_9_21": 1.0,
        "rsi_14": 50.0,
        "causal_rel_vol": 1.0,
    }
    dec_nan = engine.evaluate_proposal(sample_proposal, nan_features)
    assert dec_nan.decision_state == DecisionState.DATA_REJECTED
    assert any("Non-finite value" in flag for flag in dec_nan.diagnostics.data_quality_flags)

    # Case 3: Unapproved feature name
    extra_features = {
        "ret_1": 0.01,
        "sma_ratio_9_21": 1.0,
        "rsi_14": 50.0,
        "causal_rel_vol": 1.0,
        "unapproved_magic_feature": 42.0,
    }
    dec_extra = engine.evaluate_proposal(sample_proposal, extra_features)
    assert dec_extra.decision_state == DecisionState.DATA_REJECTED
    extra_flags = dec_extra.diagnostics.data_quality_flags
    assert any("Unapproved feature names" in flag for flag in extra_flags)


def test_model_score_alone_never_authorizes_entry(
    trained_pipeline: MLSelectionPipeline,
    frozen_policy: FrozenDecisionPolicy,
    sample_proposal: TradeProposal,
) -> None:
    """Critical SEC-06 & SEC-19 invariant: is_portfolio_entry_authorized is ALWAYS False."""
    engine = SelectiveDecisionEngine(pipeline=trained_pipeline, policy=frozen_policy)

    # Evaluate multiple feature combinations
    test_feature_sets = [
        {"ret_1": 0.05, "sma_ratio_9_21": 1.05, "rsi_14": 75.0, "causal_rel_vol": 2.5},
        {"ret_1": -0.05, "sma_ratio_9_21": 0.95, "rsi_14": 25.0, "causal_rel_vol": 1.0},
        {"ret_1": 0.09, "sma_ratio_9_21": 1.15, "rsi_14": 92.0, "causal_rel_vol": 3.0},
        {"ret_1": 0.02, "sma_ratio_9_21": 1.01, "rsi_14": 60.0, "causal_rel_vol": 50.0},
    ]

    for f_dict in test_feature_sets:
        dec = engine.evaluate_proposal(sample_proposal, f_dict)
        assert dec.is_portfolio_entry_authorized is False


def test_expectancy_does_not_subtract_fees_twice(
    trained_pipeline: MLSelectionPipeline,
    frozen_policy: FrozenDecisionPolicy,
    sample_proposal: TradeProposal,
) -> None:
    """Verify net expectancy uses historical Approach A net P&Ls without double deducting fees."""
    engine = SelectiveDecisionEngine(pipeline=trained_pipeline, policy=frozen_policy)

    features = {
        "ret_1": 0.005,
        "sma_ratio_9_21": 1.01,
        "rsi_14": 60.0,
        "causal_rel_vol": 1.2,
    }
    decision = engine.evaluate_proposal(sample_proposal, features)

    # Bin 3: empirical_prob=0.72, avg_net_win=500.00, avg_net_loss=-300.00
    # Expected formula: 0.72 * 500.00 + 0.28 * (-300.00) = 360.00 - 84.00 = 276.00
    expected_expectancy = Decimal("276.00")
    assert decision.diagnostics.estimated_net_expectancy == expected_expectancy
    assert "already deduct statutory fees" in decision.diagnostics.expectancy_formula


def test_ambiguity_flags_propagation(
    trained_pipeline: MLSelectionPipeline,
    frozen_policy: FrozenDecisionPolicy,
    sample_proposal: TradeProposal,
) -> None:
    """Verify ambiguity flags passed during evaluation are preserved in decision telemetry."""
    engine = SelectiveDecisionEngine(pipeline=trained_pipeline, policy=frozen_policy)
    features = {
        "ret_1": 0.005,
        "sma_ratio_9_21": 1.01,
        "rsi_14": 60.0,
        "causal_rel_vol": 1.2,
    }

    amb_flags = ["SAME_BAR_STOP_TARGET_COLLISION_WARNING", "SESSION_CUTOFF_RISK"]
    decision = engine.evaluate_proposal(sample_proposal, features, ambiguity_flags=amb_flags)

    assert decision.diagnostics.ambiguity_flags == amb_flags


def test_evaluate_batch_consistency(
    trained_pipeline: MLSelectionPipeline,
    frozen_policy: FrozenDecisionPolicy,
    sample_proposal: TradeProposal,
) -> None:
    """Verify batch evaluation yields bit-identical results as individual evaluations."""
    engine = SelectiveDecisionEngine(pipeline=trained_pipeline, policy=frozen_policy)
    f1 = {"ret_1": 0.05, "sma_ratio_9_21": 1.05, "rsi_14": 75.0, "causal_rel_vol": 2.5}
    f2 = {"ret_1": -0.05, "sma_ratio_9_21": 0.95, "rsi_14": 25.0, "causal_rel_vol": 1.0}

    batch_decisions = engine.evaluate_batch([(sample_proposal, f1), (sample_proposal, f2)])

    d1 = engine.evaluate_proposal(sample_proposal, f1)
    d2 = engine.evaluate_proposal(sample_proposal, f2)

    assert batch_decisions[0].decision_state == d1.decision_state
    assert batch_decisions[1].decision_state == d2.decision_state
    p0 = batch_decisions[0].diagnostics.predicted_probability
    p1 = batch_decisions[1].diagnostics.predicted_probability
    assert p0 == d1.diagnostics.predicted_probability
    assert p1 == d2.diagnostics.predicted_probability
