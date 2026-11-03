"""CLI script to generate trade-policy labels and globally chronological splits (Layer 8).

Governed by:
- docs/trade-policy-contract-v1.md
- docs/execution-policy.md
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 8 Gate: Labeling under executable trade policy, globally chronological partitions,
  boundary overlap purging, embargo from information horizon, and locked final-test lockbox.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from finpilot.data.adapters.synthetic import SyntheticDataProviderAdapter
from finpilot.data.models import MarketDataRecord
from finpilot.db.enums import DataMode
from finpilot.features.pipeline import CausalFeaturePipeline
from finpilot.labeling.generator import TradePolicyLabelGenerator
from finpilot.labeling.lockbox import FinalTestLockbox
from finpilot.labeling.models import LabelingApproach
from finpilot.labeling.split_manager import TemporalSplitManager

IST = ZoneInfo("Asia/Kolkata")


def main() -> None:
    print("=" * 70)
    print("FinPilot AI — Layer 8 Labeled Dataset and Temporal Split Generator")
    print("=" * 70)

    # 1. Generate full month of January 2026 data across 3 liquid instruments
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

        print(f"   - {symbol} (ID: {inst_id}): {len(sym_bars)} 5m bars generated.")

        # Compute point-in-time features
        feature_vectors = feature_pipeline.compute_features(sym_bars)
        features_by_time = {fv.timestamp: fv for fv in feature_vectors}

        # Generate trade-policy labels under Approach A
        sym_labels, sym_excluded = label_generator.generate_labels_for_series(
            instrument_id=inst_id,
            symbol=symbol,
            bars=sym_bars,
            features_by_time=features_by_time,
        )
        all_labels.extend(sym_labels)
        total_excluded += sym_excluded
        print(f"     => {len(sym_labels)} labeled samples generated ({sym_excluded} rows excluded).")

    dataset_hash = hashlib.sha256(raw_bars_bytes).hexdigest()
    print(f"\nTotal labeled samples generated across all instruments: {len(all_labels)}")
    print(f"Dataset SHA-256 hash: {dataset_hash}")

    # 2. Split into 5 globally chronological partitions with boundary overlap purging and embargo
    print("\n2. Partitioning into 5 globally chronological splits (50/15/10/10/15)...")
    split_manager = TemporalSplitManager(embargo_bars=75)  # 1 session embargo
    split_manifest, partitioned_data = split_manager.create_splits(
        labels=all_labels,
        dataset_hash=dataset_hash,
        policy_version="TP-V1",
        labeling_approach=LabelingApproach.APPROACH_A_SHARED_SIZING,
        total_excluded_rows=total_excluded,
    )

    print(f"\nManifest ID: {split_manifest.manifest_id}")
    print(f"Total active samples: {split_manifest.total_samples}")
    print(f"Total purged due to boundary overlap: {split_manifest.total_purged}")
    print(f"Total excluded raw rows: {split_manifest.excluded_rows_count}")
    print(f"Locked final test hash: {split_manifest.locked_final_test_hash}")

    print("\nPartition Breakdown:")
    for p_type, p_man in split_manifest.partitions.items():
        print(
            f"  - {p_type.value:<22} : {p_man.sample_count:>4} samples | "
            f"Win Rate: {p_man.win_rate * 100:>5.1f}% | "
            f"Mean P&L: ₹{p_man.mean_net_pnl:>7.2f} | "
            f"Purged: {p_man.purged_count} | "
            f"Window: {p_man.start_time.strftime('%Y-%m-%d %H:%M')} to {p_man.end_time.strftime('%Y-%m-%d %H:%M')} UTC"
        )

    # 3. Encapsulate into Lockbox and save manifest
    output_dir = Path("data/splits")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "SPLIT-MANIFEST-V1.json"

    lockbox = FinalTestLockbox(split_manifest, partitioned_data)
    lockbox.save_manifest(manifest_path)
    print(f"\nSaved split manifest to: {manifest_path}")

    print("\nFinal-Test Lockbox Verification:")
    print(f"  - Final test is locked: {lockbox.is_locked}")
    unlock_token = lockbox.generate_unlock_token()
    print(f"  - Generated unlock token: {unlock_token[:30]}...")

    print("\n=" * 70)
    print("Layer 8 Dataset and Temporal Validation Splits Generation Complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
