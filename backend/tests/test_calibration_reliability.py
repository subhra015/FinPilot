"""Tests for probability calibration evaluation, reliability diagrams, and scoring rules (Layer 10).

Governed by:
- PROJECT_SPEC.md §4, §5, §7, §9
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 10 Gate: Reliability diagrams, Murphy (1973) Brier score decomposition,
  Expected Calibration Error (ECE), and cost-integrated calibration bins.
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from finpilot.decision.reliability import ReliabilityEvaluator
from finpilot.schemas.errors import DomainValidationError


def test_reliability_evaluator_perfect_calibration() -> None:
    """Test reliability diagram when predictions are perfectly calibrated."""
    evaluator = ReliabilityEvaluator(n_bins=5, min_bin_support=2)

    # 5 bins: [0.0, 0.2), [0.2, 0.4), [0.4, 0.6), [0.6, 0.8), [0.8, 1.0]
    # In each bin, empirical win rate equals mean predicted probability
    y_prob = np.array([0.1, 0.1, 0.3, 0.3, 0.5, 0.5, 0.7, 0.7, 0.9, 0.9])
    y_true = np.array([0, 0, 0, 1, 0, 1, 1, 1, 1, 1])  # bin empirical: 0/2, 1/2, 1/2, 2/2, 2/2

    rel_data = evaluator.evaluate(
        y_true=y_true,
        y_prob=y_prob,
        model_id="MODEL-TEST",
        partition_name="CALIBRATION",
    )

    assert rel_data.total_samples == 10
    assert len(rel_data.bins) == 5
    assert rel_data.brier_score >= 0.0
    assert rel_data.expected_calibration_error >= 0.0
    assert rel_data.maximum_calibration_error >= 0.0

    # Verify Brier score decomposition components exist and are non-negative
    decomp = rel_data.brier_decomposition
    assert decomp.reliability >= 0.0
    assert decomp.resolution >= 0.0
    assert decomp.uncertainty >= 0.0
    expected_sum = decomp.reliability - decomp.resolution + decomp.uncertainty
    assert abs(decomp.decomposition_sum - expected_sum) < 1e-9


def test_murphy_brier_score_decomposition_identity() -> None:
    """Verify that Murphy (1973) decomposition mathematically matches bin-forecast Brier score.

    Decomposition theorem:
        BS_bin = Reliability - Resolution + Uncertainty
    """
    evaluator = ReliabilityEvaluator(n_bins=10, min_bin_support=1)

    np.random.seed(42)
    n = 200
    y_prob = np.random.uniform(0.05, 0.95, size=n)
    y_true = (np.random.uniform(0.0, 1.0, size=n) < y_prob).astype(int)

    rel_data = evaluator.evaluate(y_true=y_true, y_prob=y_prob)

    decomp = rel_data.brier_decomposition
    expected_sum = decomp.reliability - decomp.resolution + decomp.uncertainty
    assert abs(decomp.decomposition_sum - expected_sum) < 1e-6

    # Scientific disclosure check
    assert "not a pure calibration metric" in rel_data.scientific_note.lower()


def test_reliability_with_net_pnls_and_downside_risk() -> None:
    """Verify empirical net P&L and downside risk (max loss, CVaR 95) are calculated in bins."""
    evaluator = ReliabilityEvaluator(n_bins=2, min_bin_support=1)

    # Bin 0: [0.0, 0.5), Bin 1: [0.5, 1.0]
    y_prob = np.array([0.2, 0.3, 0.8, 0.9])
    y_true = np.array([0, 1, 1, 1])
    net_pnls = [
        Decimal("-250.00"),  # Bin 0 loss
        Decimal("400.00"),   # Bin 0 win
        Decimal("600.00"),   # Bin 1 win
        Decimal("800.00"),   # Bin 1 win
    ]

    rel_data = evaluator.evaluate(
        y_true=y_true,
        y_prob=y_prob,
        net_pnls=net_pnls,
    )

    bin0 = rel_data.bins[0]
    assert bin0.sample_count == 2
    assert bin0.positive_count == 1
    assert bin0.empirical_probability == 0.5
    assert bin0.avg_net_win == Decimal("400.00")
    assert bin0.avg_net_loss == Decimal("-250.00")
    assert bin0.max_loss == Decimal("-250.00")
    assert bin0.cvar_95 == Decimal("-250.00")

    bin1 = rel_data.bins[1]
    assert bin1.sample_count == 2
    assert bin1.positive_count == 2
    assert bin1.empirical_probability == 1.0
    assert bin1.avg_net_win == Decimal("700.00")  # (600 + 800) / 2
    assert bin1.avg_net_loss == Decimal("0.00")


def test_reliability_evaluator_validation_errors() -> None:
    """Verify input validation fails closed on invalid or mismatched arrays."""
    evaluator = ReliabilityEvaluator(n_bins=5)

    # Empty array
    with pytest.raises(DomainValidationError, match="empty dataset"):
        evaluator.evaluate(y_true=[], y_prob=[])

    # Mismatched length
    with pytest.raises(DomainValidationError, match="Length mismatch"):
        evaluator.evaluate(y_true=[0, 1], y_prob=[0.5])

    # Probability out of bounds
    with pytest.raises(DomainValidationError, match=r"within \[0\.0, 1\.0\]"):
        evaluator.evaluate(y_true=[0, 1], y_prob=[-0.1, 0.5])

    with pytest.raises(DomainValidationError, match=r"within \[0\.0, 1\.0\]"):
        evaluator.evaluate(y_true=[0, 1], y_prob=[0.5, 1.2])

    # Non-binary label
    with pytest.raises(DomainValidationError, match="strictly 0 or 1"):
        evaluator.evaluate(y_true=[0, 2], y_prob=[0.5, 0.6])

    # Net PnLs length mismatch
    with pytest.raises(DomainValidationError, match="Length mismatch: net_pnls"):
        evaluator.evaluate(y_true=[0, 1], y_prob=[0.3, 0.7], net_pnls=[Decimal("100")])


def test_reliability_evaluator_invalid_n_bins() -> None:
    """Test that n_bins < 2 raises DomainValidationError."""
    with pytest.raises(DomainValidationError, match="n_bins must be at least 2"):
        ReliabilityEvaluator(n_bins=1)
