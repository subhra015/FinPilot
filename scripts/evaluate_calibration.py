"""CLI script to evaluate probability calibration and freeze selective decision policies (Layer 10).

Governed by:
- PROJECT_SPEC.md §4, §5, §7, §9
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 10 Gate: Reliability diagrams, Murphy (1973) Brier score decomposition,
  ECE, sample support and OOD abstention, expectancy without double cost deduction,
  and frozen decision policy generation.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Ensure backend/src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "src"))

import numpy as np
from finpilot.data.adapters.synthetic import SyntheticDataProviderAdapter
from finpilot.data.models import MarketDataRecord
from finpilot.decision.engine import SelectiveDecisionEngine
from finpilot.decision.models import (
    DecisionState,
    FrozenDecisionPolicy,
)
from finpilot.decision.ood import OODDetector
from finpilot.decision.reliability import ReliabilityEvaluator
from finpilot.features.pipeline import CausalFeaturePipeline
from finpilot.labeling.generator import TradePolicyLabelGenerator
from finpilot.labeling.lockbox import FinalTestLockbox
from finpilot.labeling.models import LabelingApproach, TradePolicyLabel
from finpilot.labeling.split_manager import TemporalSplitManager
from finpilot.ml.registry import ModelRegistry
from finpilot.schemas.trade_policy import TradeProposal


def main() -> None:
    print("=" * 78)
    print("FinPilot AI — Layer 10: Calibration & Selective Decision Logic Evaluation")
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

    all_labels: list[TradePolicyLabel] = []
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
                    f"{b.symbol},{b.timestamp.isoformat()},{b.open},{b.high},{b.low},{b.close},{b.volume}\n".encode()
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

    # 2. Partition into Chronological Splits
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

    train_samples = lockbox.get_train_samples()
    cal_samples = lockbox.get_calibration_samples()
    dev_samples = lockbox.get_dev_samples()

    print(
        f"   - Partition counts: TRAIN={len(train_samples)}, "
        f"CALIBRATION={len(cal_samples)}, DEV={len(dev_samples)}"
    )

    # 3. Load Trusted Model Registry
    models_dir = Path("artifacts/models")
    registry = ModelRegistry(registry_dir=models_dir)

    cal_dir = Path("artifacts/calibration")
    cal_dir.mkdir(parents=True, exist_ok=True)

    # 4. Fit OOD Detector strictly on TRAIN features
    feature_names = ["ret_1", "sma_ratio_9_21", "rsi_14", "causal_rel_vol"]
    X_train = np.array(
        [[s.features.get(f) for f in feature_names] for s in train_samples],
        dtype=np.float64,
    )
    ood_detector = OODDetector(feature_names=feature_names)
    ood_detector.fit(X_train)
    print(f"\n3. OOD Detector fitted strictly on TRAIN ({len(X_train)} samples).")
    for feat, (b_low, b_high) in ood_detector.bounds.items():
        print(f"   - {feat}: [{b_low:.4f}, {b_high:.4f}]")

    # 5. Evaluate Calibration & Reliability for Candidates
    candidate_ids = ["MODEL-LOGREG-V1", "MODEL-LIGHTGBM-V1"]
    evaluator = ReliabilityEvaluator(n_bins=10, min_bin_support=10)

    calibration_reports: dict[str, dict] = {}

    for model_id in candidate_ids:
        print(f"\n{'=' * 78}")
        print(f"Evaluating Model: {model_id}")
        print(f"{'=' * 78}")

        pipeline, metadata = registry.load_model(model_id)
        decision_threshold = metadata.decision_threshold
        print(f"Loaded {model_id} (Family: {metadata.model_family}, Tuned Threshold: {decision_threshold:.4f})")

        # Evaluate on CALIBRATION partition
        cal_X = np.array(
            [[s.features.get(f) for f in feature_names] for s in cal_samples],
            dtype=np.float64,
        )
        cal_probs = pipeline.predict_proba_matrix(cal_X)
        cal_y = np.array([s.binary_label for s in cal_samples], dtype=np.int32)
        cal_pnls = [s.net_pnl for s in cal_samples]

        cal_rel_data = evaluator.evaluate(
            y_true=cal_y,
            y_prob=cal_probs,
            net_pnls=cal_pnls,
            model_id=model_id,
            partition_name="CALIBRATION",
        )

        print("\n--- Calibration Partition Reliability (CALIBRATION) ---")
        print(f"Total Samples: {cal_rel_data.total_samples}, Base Rate: {cal_rel_data.base_rate:.4f}")
        print(f"Brier Score: {cal_rel_data.brier_score:.4f}")
        decomp = cal_rel_data.brier_decomposition
        print(
            f"Murphy Decomposition: Reliability={decomp.reliability:.6f}, "
            f"Resolution={decomp.resolution:.6f}, Uncertainty={decomp.uncertainty:.6f} "
            f"(Sum: {decomp.decomposition_sum:.6f})"
        )
        print(f"Expected Calibration Error (ECE): {cal_rel_data.expected_calibration_error:.4f}")
        print(f"Maximum Calibration Error (MCE):  {cal_rel_data.maximum_calibration_error:.4f}")
        print(f"Log Loss:                         {cal_rel_data.log_loss:.4f}")

        print("\nCalibration Bins (CALIBRATION Split):")
        print(f"{'Bin':<4} {'Range':<12} {'N':<6} {'ObsWin%':<10} {'MeanPred':<10} {'AvgWin(₹)':<12} {'AvgLoss(₹)':<12} {'MaxLoss(₹)':<12} {'Support':<8}")
        print("-" * 88)
        for b in cal_rel_data.bins:
            rng = f"[{b.bin_lower:.2f}, {b.bin_upper:.2f})"
            sup_str = "YES" if b.has_sufficient_support else "LOW (<10)"
            print(
                f"{b.bin_index:<4} {rng:<12} {b.sample_count:<6} {b.empirical_probability*100:>7.1f}%   "
                f"{b.mean_predicted_probability:>8.4f}   {b.avg_net_win!s:>10}   {b.avg_net_loss!s:>10}   "
                f"{b.max_loss!s:>10}   {sup_str:<8}"
            )

        # Freeze Decision Policy (DECISION-POLICY-V1)
        coverage_rate = float(np.mean(cal_probs >= decision_threshold))
        frozen_policy = FrozenDecisionPolicy(
            policy_id="DECISION-POLICY-V1",
            model_id=model_id,
            decision_threshold=decision_threshold,
            min_bin_sample_support=10,
            min_expectancy=Decimal("0.00"),
            ood_bounds=ood_detector.get_bounds_dict(),
            calibration_bins=cal_rel_data.bins,
            coverage_rate=round(coverage_rate, 4),
            frozen_at=datetime.now(UTC),
            policy_hash="placeholder",
        )
        frozen_policy = frozen_policy.model_copy(
            update={"policy_hash": frozen_policy.calculate_policy_hash()}
        )

        policy_file = cal_dir / f"DECISION-POLICY-V1-{model_id}.json"
        with open(policy_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(frozen_policy.model_dump(mode="json"), indent=2))
        print(f"\nFrozen Decision Policy saved: {policy_file} (Hash: {frozen_policy.policy_hash[:16]}...)")

        # Evaluate on DEV_MODEL_SELECTION partition using SelectiveDecisionEngine
        engine = SelectiveDecisionEngine(
            pipeline=pipeline,
            policy=frozen_policy,
            ood_detector=ood_detector,
        )

        dev_decisions = []
        state_counts: dict[DecisionState, int] = {s: 0 for s in DecisionState}

        for idx, sample in enumerate(dev_samples):
            prop = TradeProposal(
                proposal_id=f"PROP-DEV-{idx+1:04d}",
                instrument_id=sample.instrument_id,
                symbol=sample.symbol,
                decision_timestamp=sample.decision_time,
                earliest_entry_timestamp=sample.entry_time,
                entry_price=sample.entry_price,
                stop_loss=Decimal(str(round(float(sample.entry_price) * 0.99, 2))),
                target_price=Decimal(str(round(float(sample.entry_price) * 1.02, 2))),
                quantity=sample.quantity,
            )
            dec = engine.evaluate_proposal(prop, sample.features)
            dev_decisions.append(dec)
            state_counts[dec.decision_state] += 1

        print("\n--- Selective Decision Engine Outcomes (DEV_MODEL_SELECTION) ---")
        total_dev = len(dev_decisions)
        for state, count in state_counts.items():
            pct = (count / total_dev * 100.0) if total_dev > 0 else 0.0
            print(f"   - {state.value:<22}: {count:>4} ({pct:>5.1f}%)")

        # Invariant checks
        authorized_count = sum(1 for d in dev_decisions if d.is_portfolio_entry_authorized)
        assert authorized_count == 0, "CRITICAL ERROR: A model score authorized a portfolio entry directly!"
        print("\n   [PASS] Verified invariant: is_portfolio_entry_authorized is FALSE across 100% of decisions.")

        calibration_reports[model_id] = {
            "model_id": model_id,
            "decision_threshold": decision_threshold,
            "policy_hash": frozen_policy.policy_hash,
            "calibration_metrics": cal_rel_data.model_dump(mode="json"),
            "dev_state_distribution": {s.value: c for s, c in state_counts.items()},
            "invariant_checked": True,
        }

    # 6. Save Comprehensive Calibration Report
    report_path = cal_dir / "calibration_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(calibration_reports, f, indent=2)
    print(f"\n{'=' * 78}")
    print(f"Calibration Report generated: {report_path}")
    print(f"{'=' * 78}")


if __name__ == "__main__":
    main()
