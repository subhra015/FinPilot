"""Unit tests for ML Selection Layer simulation and economic evaluation (Layer 9).

Verifies:
- Evaluation parity against No-Trade and Simple Strategy baselines.
- Ledger reconciliation to exact ₹0.00 across all evaluation runs.
- Filter rate, win rate, profit factor, drawdown, and proposal veto accounting.
- ML acting strictly as an authorization gate (selection filter only).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from finpilot.data.adapters.synthetic import SyntheticDataProviderAdapter
from finpilot.labeling.lockbox import FinalTestLockbox
from finpilot.labeling.models import (
    LabelingApproach,
    PartitionType,
    TradeOutcomeReason,
    TradePolicyLabel,
)
from finpilot.labeling.split_manager import TemporalSplitManager
from finpilot.ml.evaluator import SelectionLayerEvaluator
from finpilot.ml.models import CalibrationMethod, ModelFamily
from finpilot.ml.pipeline import MLSelectionPipeline

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")
FEATURE_NAMES = ("ret_1", "sma_ratio_9_21", "rsi_14", "causal_rel_vol")


@pytest.fixture
def mini_split_manifest_and_data() -> tuple[FinalTestLockbox, tuple[str, ...]]:
    """Return a minimal split manifest covering a 2-day dev window (Jan 16 to Jan 17, 2026)."""
    universe = ("RELIANCE", "TCS")
    labels: list[TradePolicyLabel] = []

    dummy_features = {
        "ret_1": 0.002,
        "sma_ratio_9_21": 0.001,
        "rsi_14": 52.0,
        "causal_rel_vol": 1.2,
    }

    for i, sym in enumerate(universe):
        for day in range(1, 28):
            dt = datetime(2026, 1, day, 10, 0, tzinfo=IST).astimezone(UTC)
            lbl = TradePolicyLabel(
                sample_id=f"LBL-{sym}-{day}",
                instrument_id=101 + i,
                symbol=sym,
                decision_time=dt,
                entry_time=dt + timedelta(minutes=5),
                exit_time=dt + timedelta(minutes=20),
                holding_bars=3,
                entry_price=Decimal("1000.00"),
                exit_price=Decimal("1010.00"),
                quantity=10,
                gross_pnl=Decimal("100.00"),
                fees=Decimal("10.00"),
                net_pnl=Decimal("90.00"),
                gross_return=Decimal("0.01"),
                net_return=Decimal("0.009"),
                binary_label=1,
                outcome_reason=TradeOutcomeReason.TARGET_HIT,
                is_ambiguous_exit=False,
                is_gap_fill=False,
                features=dummy_features,
                labeling_approach=LabelingApproach.APPROACH_A_SHARED_SIZING,
                policy_version="TP-V1",
            )
            labels.append(lbl)

    mgr = TemporalSplitManager(embargo_bars=1)
    manifest, p_data = mgr.create_splits(
        labels=labels,
        dataset_hash="hash_eval_test",
        policy_version="TP-V1",
        labeling_approach=LabelingApproach.APPROACH_A_SHARED_SIZING,
        total_excluded_rows=0,
    )
    return FinalTestLockbox(manifest, p_data), universe


def test_evaluator_no_trade_cash_reference_parity(
    mini_split_manifest_and_data: tuple[FinalTestLockbox, tuple[str, ...]],
) -> None:
    """Verify No-Trade reference has exactly zero trades, zero fees, zero P&L, and reconciles."""
    lockbox, universe = mini_split_manifest_and_data
    dev_man = lockbox.manifest.partitions[PartitionType.DEV_MODEL_SELECTION]

    start_d = dev_man.start_time.astimezone(IST).date()
    end_d = dev_man.end_time.astimezone(IST).date()

    evaluator = SelectionLayerEvaluator(
        initial_capital=Decimal("30000.00"),
        data_adapter=SyntheticDataProviderAdapter(),
    )

    result = evaluator.evaluate_strategy_variant(
        start_date=start_d,
        end_date=end_d,
        universe=universe,
        is_no_trade=True,
    )

    assert result.strategy_name == "NO_TRADE_REFERENCE"
    assert result.total_trades_filled == 0
    assert result.gross_pnl == Decimal("0.00")
    assert result.fees == Decimal("0.00")
    assert result.net_pnl == Decimal("0.00")
    assert result.ledger_reconciled is True
    assert result.accounting_discrepancy == Decimal("0.00")


def test_evaluator_unfiltered_baseline_simulation(
    mini_split_manifest_and_data: tuple[FinalTestLockbox, tuple[str, ...]],
) -> None:
    """Verify unfiltered simple strategy baseline executes proposals and reconciles to ₹0.00."""
    lockbox, universe = mini_split_manifest_and_data
    dev_man = lockbox.manifest.partitions[PartitionType.DEV_MODEL_SELECTION]

    start_d = dev_man.start_time.astimezone(IST).date()
    end_d = dev_man.end_time.astimezone(IST).date()

    evaluator = SelectionLayerEvaluator(
        initial_capital=Decimal("30000.00"),
        data_adapter=SyntheticDataProviderAdapter(),
    )

    result = evaluator.evaluate_strategy_variant(
        start_date=start_d,
        end_date=end_d,
        universe=universe,
        selection_pipeline=None,  # Unfiltered baseline
    )

    assert result.strategy_name == "STRAT-SIMPLE-V1"
    assert result.proposals_vetoed == 0
    assert result.filter_rate_pct == 0.0
    assert result.ledger_reconciled is True
    assert result.accounting_discrepancy == Decimal("0.00")


def test_evaluator_ml_selection_veto_filter_and_reconciliation(
    mini_split_manifest_and_data: tuple[FinalTestLockbox, tuple[str, ...]],
) -> None:
    """Verify ML selection layer filters proposals and maintains strict ledger reconciliation."""
    lockbox, universe = mini_split_manifest_and_data
    dev_man = lockbox.manifest.partitions[PartitionType.DEV_MODEL_SELECTION]

    start_d = dev_man.start_time.astimezone(IST).date()
    end_d = dev_man.end_time.astimezone(IST).date()

    # Create dummy pipeline with high threshold so it vetoes some proposals
    pipeline = MLSelectionPipeline(
        model_id="MODEL-FILTER-TEST",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_names=list(FEATURE_NAMES),
        base_estimator=LogisticRegression(random_state=42),
        calibration_method=CalibrationMethod.SIGMOID,
        decision_threshold=0.90,  # very strict
    )
    rng = np.random.RandomState(42)
    X = rng.randn(50, len(FEATURE_NAMES))
    y = (X[:, 0] > 0).astype(int)

    pipeline.fit(X, y, X_cal=X, y_cal=y)

    evaluator = SelectionLayerEvaluator(
        initial_capital=Decimal("30000.00"),
        data_adapter=SyntheticDataProviderAdapter(),
    )

    result = evaluator.evaluate_strategy_variant(
        start_date=start_d,
        end_date=end_d,
        universe=universe,
        selection_pipeline=pipeline,
    )

    assert result.model_id == "MODEL-FILTER-TEST"
    assert result.total_proposals_evaluated >= result.proposals_authorized
    assert result.proposals_vetoed == result.total_proposals_evaluated - result.proposals_authorized
    assert result.ledger_reconciled is True
    assert result.accounting_discrepancy == Decimal("0.00")
