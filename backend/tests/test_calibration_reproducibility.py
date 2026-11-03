"""Reproducibility and cryptographic lockbox tests for calibration and selective decision logic.

Governed by:
- PROJECT_SPEC.md §4, §5, §7, §9
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 10 Gate: Bit-identical calibration reproducibility, frozen policy integrity hash,
  and zero access to LOCKED_FINAL_TEST partition.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from finpilot.decision.engine import SelectiveDecisionEngine
from finpilot.decision.models import (
    CalibrationBin,
    DecisionState,
    FrozenDecisionPolicy,
)
from finpilot.decision.reliability import ReliabilityEvaluator
from finpilot.labeling.lockbox import FinalTestLockbox
from finpilot.labeling.models import (
    LabelingApproach,
    TradeOutcomeReason,
    TradePolicyLabel,
)
from finpilot.labeling.split_manager import FinalTestLockedError, TemporalSplitManager
from finpilot.ml.registry import ModelRegistry
from finpilot.schemas.trade_policy import TradeProposal


def test_frozen_decision_policy_hash_integrity() -> None:
    """Verify that FrozenDecisionPolicy computes a deterministic SHA-256 integrity hash."""
    bins = [
        CalibrationBin(
            bin_index=0,
            bin_lower=0.0,
            bin_upper=0.5,
            sample_count=50,
            positive_count=10,
            empirical_probability=0.20,
            mean_predicted_probability=0.25,
            avg_net_win=Decimal("300.00"),
            avg_net_loss=Decimal("-250.00"),
            max_loss=Decimal("-300.00"),
            cvar_95=Decimal("-300.00"),
            has_sufficient_support=True,
        ),
        CalibrationBin(
            bin_index=1,
            bin_lower=0.5,
            bin_upper=1.0,
            sample_count=50,
            positive_count=35,
            empirical_probability=0.70,
            mean_predicted_probability=0.72,
            avg_net_win=Decimal("450.00"),
            avg_net_loss=Decimal("-250.00"),
            max_loss=Decimal("-300.00"),
            cvar_95=Decimal("-300.00"),
            has_sufficient_support=True,
        ),
    ]

    policy1 = FrozenDecisionPolicy(
        policy_id="DECISION-POLICY-V1",
        model_id="MODEL-LOGREG-V1",
        decision_threshold=0.54,
        min_bin_sample_support=10,
        min_expectancy=Decimal("0.00"),
        ood_bounds={"ret_1": [-0.10, 0.10]},
        calibration_bins=bins,
        coverage_rate=0.45,
        frozen_at=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
        policy_hash="placeholder",
    )
    hash1 = policy1.calculate_policy_hash()

    policy2 = FrozenDecisionPolicy(
        policy_id="DECISION-POLICY-V1",
        model_id="MODEL-LOGREG-V1",
        decision_threshold=0.54,
        min_bin_sample_support=10,
        min_expectancy=Decimal("0.00"),
        ood_bounds={"ret_1": [-0.10, 0.10]},
        calibration_bins=bins,
        coverage_rate=0.45,
        frozen_at=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
        policy_hash="different_placeholder",
    )
    hash2 = policy2.calculate_policy_hash()

    # Integrity hash is identical regardless of placeholder
    assert hash1 == hash2
    assert len(hash1) == 64

    # Any parameter alteration mutates hash
    policy_mutated = policy1.model_copy(update={"decision_threshold": 0.55})
    assert policy_mutated.calculate_policy_hash() != hash1


def test_zero_access_to_locked_final_test_partition() -> None:
    """SEC-19: Assert that LOCKED_FINAL_TEST remains strictly sealed during calibration."""
    split_mgr = TemporalSplitManager(embargo_bars=0)
    base_time = datetime(2026, 1, 5, 9, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    labels = []
    for i in range(25):
        utc_ts = (base_time + timedelta(minutes=5 * i)).astimezone(UTC)
        labels.append(
            TradePolicyLabel(
                sample_id=f"LBL-TEST-{i:03d}",
                instrument_id=101,
                symbol="RELIANCE",
                decision_time=utc_ts,
                entry_time=utc_ts + timedelta(minutes=5),
                exit_time=utc_ts + timedelta(minutes=10),
                holding_bars=1,
                entry_price=Decimal("2500.00"),
                exit_price=Decimal("2525.00"),
                quantity=10,
                gross_pnl=Decimal("250.00"),
                fees=Decimal("20.00"),
                net_pnl=Decimal("230.00"),
                gross_return=Decimal("0.0100"),
                net_return=Decimal("0.0092"),
                binary_label=1,
                outcome_reason=TradeOutcomeReason.TARGET_HIT,
                is_ambiguous_exit=False,
                is_gap_fill=False,
                pit_universe_eligible=True,
                features={"ret_1": 0.001, "sma_ratio_9_21": 1.002},
                policy_version="TP-V1",
                labeling_approach=LabelingApproach.APPROACH_A_SHARED_SIZING,
            )
        )

    manifest, partitioned = split_mgr.create_splits(labels, dataset_hash="test_cal_lockbox")
    lockbox = FinalTestLockbox(manifest, partitioned)

    # Attempting to load final test samples without approval token must fail closed
    with pytest.raises(FinalTestLockedError, match="Access to LOCKED_FINAL_TEST is blocked"):
        lockbox.get_final_test_samples()


def test_reliability_evaluation_bit_identical_determinism() -> None:
    """Verify that ReliabilityEvaluator produces bit-identical metrics on identical inputs."""
    evaluator = ReliabilityEvaluator(n_bins=10, min_bin_support=5)

    np.random.seed(12345)
    y_prob = np.random.uniform(0.0, 1.0, size=300)
    y_true = (np.random.uniform(0.0, 1.0, size=300) < y_prob).astype(int)
    net_pnls = [Decimal(str(round(np.random.normal(50.0, 200.0), 2))) for _ in range(300)]

    run1 = evaluator.evaluate(y_true, y_prob, net_pnls=net_pnls, model_id="MODEL-RUN1")
    run2 = evaluator.evaluate(y_true, y_prob, net_pnls=net_pnls, model_id="MODEL-RUN1")

    assert run1.brier_score == run2.brier_score
    assert run1.expected_calibration_error == run2.expected_calibration_error
    assert run1.maximum_calibration_error == run2.maximum_calibration_error
    assert run1.log_loss == run2.log_loss
    assert run1.brier_decomposition == run2.brier_decomposition
    assert len(run1.bins) == len(run2.bins)

    for b1, b2 in zip(run1.bins, run2.bins, strict=True):
        assert b1.sample_count == b2.sample_count
        assert b1.positive_count == b2.positive_count
        assert b1.empirical_probability == b2.empirical_probability
        assert b1.avg_net_win == b2.avg_net_win
        assert b1.avg_net_loss == b2.avg_net_loss
        assert b1.cvar_95 == b2.cvar_95


def test_real_saved_model_registry_integration() -> None:
    """Test end-to-end integration with ModelRegistry loading MODEL-LOGREG-V1."""
    models_dir = Path("artifacts/models")
    if not (models_dir / "MODEL-LOGREG-V1" / "metadata.json").exists():
        pytest.skip("MODEL-LOGREG-V1 artifact not present in workspace.")

    registry = ModelRegistry(registry_dir=models_dir)
    pipeline, metadata = registry.load_model("MODEL-LOGREG-V1")

    assert metadata.model_id == "MODEL-LOGREG-V1"
    assert pipeline.is_fitted is True

    # Build calibration bins and policy for loaded pipeline
    evaluator = ReliabilityEvaluator(n_bins=5, min_bin_support=1)
    y_true = [0, 0, 1, 1, 1]
    y_prob = [0.1, 0.3, 0.5, 0.7, 0.9]
    rel_data = evaluator.evaluate(y_true=y_true, y_prob=y_prob, model_id="MODEL-LOGREG-V1")

    policy = FrozenDecisionPolicy(
        policy_id="DECISION-POLICY-V1",
        model_id="MODEL-LOGREG-V1",
        decision_threshold=metadata.decision_threshold,
        min_bin_sample_support=1,
        min_expectancy=Decimal("0.00"),
        ood_bounds={
            "ret_1": [-0.10, 0.10],
            "rsi_14": [0.0, 100.0],
            "sma_ratio_9_21": [0.8, 1.2],
            "causal_rel_vol": [0.0, 10.0],
        },
        calibration_bins=rel_data.bins,
        coverage_rate=0.50,
        frozen_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        policy_hash="mock",
    )
    policy = policy.model_copy(update={"policy_hash": policy.calculate_policy_hash()})

    engine = SelectiveDecisionEngine(pipeline=pipeline, policy=policy)

    features = {
        "ret_1": 0.01,
        "sma_ratio_9_21": 1.02,
        "rsi_14": 65.0,
        "causal_rel_vol": 1.5,
    }
    proposal = TradeProposal(
        proposal_id="PROP-REGISTRY-001",
        instrument_id=101,
        symbol="RELIANCE",
        decision_timestamp=datetime(2026, 1, 15, 5, 25, tzinfo=UTC),
        earliest_entry_timestamp=datetime(2026, 1, 15, 5, 30, tzinfo=UTC),
        entry_price=Decimal("2500.00"),
        stop_loss=Decimal("2475.00"),
        target_price=Decimal("2550.00"),
        quantity=12,
    )

    decision = engine.evaluate_proposal(proposal, features)
    assert decision.decision_state in (DecisionState.ACCEPTED_CANDIDATE, DecisionState.NO_TRADE)
    assert decision.is_portfolio_entry_authorized is False
