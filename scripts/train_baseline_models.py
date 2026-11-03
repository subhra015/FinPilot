"""CLI script to train and evaluate baseline ML selection models (Layer 9).

Governed by:
- PROJECT_SPEC.md §4, §5, §7, §9
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 9 Acceptance Gate: Approved candidates (Logistic Regression + LightGBM),
  training-only fit, calibration on CALIBRATION split, no final-test access,
  safe model loading, and economic evaluation as a selection layer.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from finpilot.data.adapters.synthetic import SyntheticDataProviderAdapter
from finpilot.data.models import MarketDataRecord
from finpilot.features.pipeline import CausalFeaturePipeline
from finpilot.labeling.generator import TradePolicyLabelGenerator
from finpilot.labeling.lockbox import FinalTestLockbox
from finpilot.labeling.models import LabelingApproach, PartitionType
from finpilot.labeling.split_manager import TemporalSplitManager
from finpilot.ml.evaluator import SelectionLayerEvaluator
from finpilot.ml.registry import ModelRegistry
from finpilot.ml.trainer import MLModelTrainer


def main() -> None:
    print("=" * 78)
    print("FinPilot AI — Layer 9: Baseline ML Candidate Training & Validation Selection")
    print("=" * 78)

    # 1. Ingest Market Data for January 2026 across 3 liquid instruments
    symbols = [("RELIANCE", 101), ("TCS", 102), ("INFY", 103)]
    start_date = date(2026, 1, 1)
    end_date = date(2026, 1, 31)

    print(
        f"\n1. Ingesting market candles for {len(symbols)} instruments "
        f"({start_date} to {end_date})..."
    )
    data_adapter = SyntheticDataProviderAdapter()
    feature_pipeline = CausalFeaturePipeline()
    label_generator = TradePolicyLabelGenerator(
        labeling_approach=LabelingApproach.APPROACH_A_SHARED_SIZING
    )

    all_labels = []
    total_excluded = 0
    raw_bars_bytes = bytearray()

    for symbol, inst_id in symbols:
        curr = start_date
        sym_bars: list[MarketDataRecord] = []
        while curr <= end_date:
            session_bars = data_adapter.fetch_bars(symbol, curr)
            sym_bars.extend(session_bars)
            for b in session_bars:
                raw_bars_bytes.extend(
                    f"{b.symbol},{b.timestamp.isoformat()},{b.open},{b.high},{b.low},{b.close},{b.volume}\n".encode(
                        "utf-8"
                    )
                )
            curr += timedelta(days=1)

        feature_vectors = feature_pipeline.compute_features(sym_bars)
        features_by_time = {fv.timestamp: fv for fv in feature_vectors}

        sym_labels, sym_excluded = label_generator.generate_labels_for_series(
            instrument_id=inst_id,
            symbol=symbol,
            bars=sym_bars,
            features_by_time=features_by_time,
        )
        all_labels.extend(sym_labels)
        total_excluded += sym_excluded
        print(f"   - {symbol} (ID: {inst_id}): {len(sym_labels)} labels generated.")

    dataset_hash = hashlib.sha256(raw_bars_bytes).hexdigest()
    print(f"\nTotal labeled samples: {len(all_labels)} (Dataset Hash: {dataset_hash[:16]}...)")

    # 2. Partition into 5 Globally Chronological Splits
    print("\n2. Applying temporal splits with boundary purging & 1-session embargo...")
    split_manager = TemporalSplitManager(embargo_bars=75)
    split_manifest, partitioned_data = split_manager.create_splits(
        labels=all_labels,
        dataset_hash=dataset_hash,
        policy_version="TP-V1",
        labeling_approach=LabelingApproach.APPROACH_A_SHARED_SIZING,
        total_excluded_rows=total_excluded,
    )

    lockbox = FinalTestLockbox(split_manifest, partitioned_data)
    print(f"   - Manifest ID: {split_manifest.manifest_id}")
    print(
        f"   - Final Test Sealed: {lockbox.is_locked} "
        f"(Lock Hash: {split_manifest.locked_final_test_hash[:16]}...)"
    )

    # Safe partitions: strictly exclude final test
    safe_partitions = {
        PartitionType.TRAIN: lockbox.get_train_samples(),
        PartitionType.CALIBRATION: lockbox.get_calibration_samples(),
        PartitionType.THRESHOLD_SELECTION: lockbox.get_threshold_samples(),
        PartitionType.DEV_MODEL_SELECTION: lockbox.get_dev_samples(),
    }

    # 3. Initialize Model Registry and Trainer
    models_dir = Path("artifacts/models")
    registry = ModelRegistry(registry_dir=models_dir)
    trainer = MLModelTrainer(
        split_manifest=split_manifest,
        partitions=safe_partitions,
        registry=registry,
    )

    # 4. Train Model Candidate 1: Logistic Regression (L2, Sigmoid Calibration)
    print(
        "\n3. Training Candidate 1: MODEL-LOGREG-V1 "
        "(Logistic Regression + Sigmoid Calibration)..."
    )
    logreg_pipeline, logreg_meta = trainer.train_logistic_regression(
        model_id="MODEL-LOGREG-V1",
        C=1.0,
        random_state=42,
    )
    print(f"   - Artifact Checksum: {logreg_meta.artifact_checksum}")
    print(f"   - Decision Threshold: {logreg_meta.decision_threshold:.4f}")
    print(
        f"   - Validation Accuracy: {logreg_meta.validation_metrics.accuracy * 100:.1f}% | "
        f"ROC-AUC: {logreg_meta.validation_metrics.roc_auc:.4f} | "
        f"PR-AUC: {logreg_meta.validation_metrics.pr_auc:.4f} | "
        f"Brier: {logreg_meta.validation_metrics.brier_score:.4f}"
    )

    # 5. Train Model Candidate 2: LightGBM (Constrained Depth, Isotonic Calibration)
    print(
        "\n4. Training Candidate 2: MODEL-LIGHTGBM-V1 "
        "(LightGBM max_depth=3 + Isotonic Calibration)..."
    )
    lgb_pipeline, lgb_meta = trainer.train_lightgbm(
        model_id="MODEL-LIGHTGBM-V1",
        n_estimators=100,
        max_depth=3,
        num_leaves=7,
        learning_rate=0.05,
        random_state=42,
    )
    print(f"   - Artifact Checksum: {lgb_meta.artifact_checksum}")
    print(f"   - Decision Threshold: {lgb_meta.decision_threshold:.4f}")
    print(
        f"   - Validation Accuracy: {lgb_meta.validation_metrics.accuracy * 100:.1f}% | "
        f"ROC-AUC: {lgb_meta.validation_metrics.roc_auc:.4f} | "
        f"PR-AUC: {lgb_meta.validation_metrics.pr_auc:.4f} | "
        f"Brier: {lgb_meta.validation_metrics.brier_score:.4f}"
    )

    # 6. Evaluate as Selection Layer over Event-Driven Simulator (DEV Window)
    print("\n5. Running Economic Selection Layer Evaluation over DEV_MODEL_SELECTION window...")
    evaluator = SelectionLayerEvaluator(
        initial_capital=Decimal("30000.00"),
        data_adapter=data_adapter,
    )

    dev_comparison = evaluator.compare_models_on_validation(
        split_manifest=split_manifest,
        candidate_models={
            "MODEL-LOGREG-V1": logreg_pipeline,
            "MODEL-LIGHTGBM-V1": lgb_pipeline,
        },
        universe=("RELIANCE", "TCS", "INFY"),
    )

    # 7. Print Performance Comparison Table for DEV window
    print("\n" + "=" * 115)
    print("A. DEV_MODEL_SELECTION EVALUATION (Jan 16 to Jan 20, 2026 — Frozen Validation Window)")
    print("=" * 115)
    header = (
        f"{'Variant / Strategy':<26} | {'Proposals':<10} | {'Filter%':<8} | {'Trades':<7} | "
        f"{'Win Rate':<9} | {'Gross P&L':<11} | {'Fees':<9} | {'Net P&L':<11} | "
        f"{'Profit Factor':<13} | {'Max DD':<9} | {'Reconciled'}"
    )
    print(header)
    print("-" * 115)

    dev_variants = [
        ("No-Trade Reference", dev_comparison.no_trade_result),
        ("Unfiltered Simple Baseline", dev_comparison.simple_baseline_result),
        ("MODEL-LOGREG-V1 Filter", dev_comparison.ml_candidate_results["MODEL-LOGREG-V1"]),
        ("MODEL-LIGHTGBM-V1 Filter", dev_comparison.ml_candidate_results["MODEL-LIGHTGBM-V1"]),
    ]

    for name, res in dev_variants:
        rec_status = (
            "PASS (₹0.00)" if res.ledger_reconciled else f"FAIL (₹{res.accounting_discrepancy})"
        )
        print(
            f"{name:<26} | {res.total_proposals_evaluated:>10} | {res.filter_rate_pct:>7.1f}% | "
            f"{res.total_trades_filled:>7} | {res.win_rate * 100:>8.1f}% | "
            f"₹{res.gross_pnl:>9.2f} | ₹{res.fees:>7.2f} | ₹{res.net_pnl:>9.2f} | "
            f"{res.profit_factor:>13.2f} | ₹{res.max_drawdown_amount:>7.2f} | {rec_status}"
        )
    print("=" * 115)

    # 8. Diagnostic Evaluation on Active Trading Window (Jan 1 to Jan 15, 2026)
    print("\n" + "=" * 115)
    print("B. ACTIVE TRADING SESSIONS DIAGNOSTIC (Jan 1 to Jan 15, 2026 — Active Proposals)")
    print("=" * 115)
    print(header)
    print("-" * 115)

    train_start = date(2026, 1, 1)
    train_end = date(2026, 1, 15)
    u_tuple = ("RELIANCE", "TCS", "INFY")

    b_no_trade = evaluator.evaluate_strategy_variant(
        train_start, train_end, u_tuple, is_no_trade=True
    )
    b_unfiltered = evaluator.evaluate_strategy_variant(
        train_start, train_end, u_tuple, selection_pipeline=None
    )
    b_logreg = evaluator.evaluate_strategy_variant(
        train_start, train_end, u_tuple, selection_pipeline=logreg_pipeline
    )
    b_lgb = evaluator.evaluate_strategy_variant(
        train_start, train_end, u_tuple, selection_pipeline=lgb_pipeline
    )

    train_variants = [
        ("No-Trade Reference", b_no_trade),
        ("Unfiltered Simple Baseline", b_unfiltered),
        ("MODEL-LOGREG-V1 Filter", b_logreg),
        ("MODEL-LIGHTGBM-V1 Filter", b_lgb),
    ]

    for name, res in train_variants:
        rec_status = (
            "PASS (₹0.00)" if res.ledger_reconciled else f"FAIL (₹{res.accounting_discrepancy})"
        )
        print(
            f"{name:<26} | {res.total_proposals_evaluated:>10} | {res.filter_rate_pct:>7.1f}% | "
            f"{res.total_trades_filled:>7} | {res.win_rate * 100:>8.1f}% | "
            f"₹{res.gross_pnl:>9.2f} | ₹{res.fees:>7.2f} | ₹{res.net_pnl:>9.2f} | "
            f"{res.profit_factor:>13.2f} | ₹{res.max_drawdown_amount:>7.2f} | {rec_status}"
        )
    print("=" * 115)

    print("\nRecommendation for DEV Split: BASELINE / NO-TRADE")
    print(f"Rationale: {dev_comparison.recommendation_rationale}")

    # 9. Save comparison report
    comparison_file = models_dir / "model_selection_comparison.json"
    with open(comparison_file, "w", encoding="utf-8") as f:
        json.dump(dev_comparison.model_dump(mode="json"), f, indent=2, sort_keys=True)
    print(f"\nSaved validation comparison report to: {comparison_file}")
    print("=" * 78)


if __name__ == "__main__":
    main()
