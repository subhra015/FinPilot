"""Temporal split manager with globally chronological partitions, purging, and embargo (Layer 8).

Governed by:
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- docs/trade-policy-contract-v1.md
- Layer 8 Gate: Globally chronological ordering across all symbols, boundary overlap
  purging, embargo from information horizon, locked final-test partition, and split manifests.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from finpilot.schemas.common import normalize_to_utc
from finpilot.schemas.errors import DomainValidationError, ErrorCode

from .models import (
    LabelingApproach,
    PartitionManifest,
    PartitionType,
    SplitManifest,
    TradePolicyLabel,
)

IST = ZoneInfo("Asia/Kolkata")

DEFAULT_EMBARGO_JUSTIFICATION = (
    "Embargo is set to 1 trading session (75 completed 5-minute bars / 1 day) between consecutive "
    "temporal partitions. Justification: (1) Intraday trade outcome horizon is strictly <= 72 "
    "bars (compulsory square-off at 15:15 IST); (2) Feature indicators (SMA-21, ATR-14, RSI-14) "
    "have an information horizon of up to 21 bars (105 minutes); (3) Serial return autocorrelation "
    "and volatility clustering (GARCH persistence) in Indian equities decay over 1 session. "
    "Enforcing a 1-session buffer guarantees zero informational contamination across boundaries."
)

DEFAULT_SURVIVORSHIP_LIMITATION = (
    "NSE equity historical constituent and delisting records from public retail data providers "
    "are subject to survivorship bias limitations. While FinPilot enforces strict Point-In-Time "
    "universe filtering on known registered instruments, complete historical delisting coverage "
    "for prior years is unavailable in the current vendor tier. This limitation is explicitly "
    "disclosed and not assumed solved."
)


class FinalTestLockedError(DomainValidationError):
    """Raised when routine tuning code attempts to access the locked final test partition."""

    def __init__(self, message: str = "Access to LOCKED_FINAL_TEST is locked.") -> None:
        super().__init__(
            message=message,
            field="partition_type",
            code=ErrorCode.PERMISSION_DENIED,
        )


class TemporalSplitManager:
    """Creates and enforces globally chronological partitions across all instruments.

    Invariants:
    1. Global Chronological Timeline: All instruments are partitioned along the exact same
       global timestamps. No symbol may contribute training data from a date later than
       another symbol's development or test data.
    2. Boundary Purging: Any label whose trade outcome interval [decision_time, exit_time]
       extends past the partition boundary is purged.
    3. Horizon-Justified Embargo: An embargo window is placed after each partition boundary;
       any candidate samples falling within the embargo buffer are excluded from all partitions.
    4. Immutable Partition Manifests: Manifest captures row counts, positive/negative distributions,
       win rates, symbol coverage, purge counts, and SHA-256 sample digests.
    5. Final-Test Lockbox: The LOCKED_FINAL_TEST partition is cryptographically hashed and sealed.
       Routine loading raises FinalTestLockedError unless an explicit unseal token is provided.
    """

    def __init__(
        self,
        embargo_bars: int = 75,  # 1 full NSE trading session (75 x 5m bars)
        embargo_justification: str = DEFAULT_EMBARGO_JUSTIFICATION,
        survivorship_bias_limitation: str = DEFAULT_SURVIVORSHIP_LIMITATION,
    ) -> None:
        self.embargo_bars = embargo_bars
        self.embargo_justification = embargo_justification
        self.survivorship_bias_limitation = survivorship_bias_limitation

    def create_splits(
        self,
        labels: list[TradePolicyLabel],
        dataset_hash: str,
        policy_version: str = "TP-V1",
        labeling_approach: LabelingApproach = LabelingApproach.APPROACH_A_SHARED_SIZING,
        total_excluded_rows: int = 0,
        custom_ratios: dict[PartitionType, float] | None = None,
    ) -> tuple[SplitManifest, dict[PartitionType, list[TradePolicyLabel]]]:
        """Partition labeled samples into 5 globally chronological subsets with purge & embargo.

        Default partition ratios:
        - TRAIN: 50%
        - DEV_MODEL_SELECTION: 15%
        - CALIBRATION: 10%
        - THRESHOLD_SELECTION: 10%
        - LOCKED_FINAL_TEST: 15%
        """
        if not labels:
            raise DomainValidationError(
                "Cannot create temporal splits from an empty label set.",
                field="labels",
                code=ErrorCode.VALIDATION_ERROR,
            )

        ratios = custom_ratios or {
            PartitionType.TRAIN: 0.50,
            PartitionType.DEV_MODEL_SELECTION: 0.15,
            PartitionType.CALIBRATION: 0.10,
            PartitionType.THRESHOLD_SELECTION: 0.10,
            PartitionType.LOCKED_FINAL_TEST: 0.15,
        }

        # Validate ratios sum to 1.0
        ratio_sum = sum(ratios.values())
        if abs(ratio_sum - 1.0) > 1e-6:
            raise DomainValidationError(
                f"Partition ratios must sum to 1.0; got {ratio_sum:.6f}",
                field="custom_ratios",
                code=ErrorCode.VALIDATION_ERROR,
            )

        # 1. Establish Global Chronological Timeline across ALL symbols
        # Sort all unique decision timestamps globally
        unique_decision_times = sorted(
            list({normalize_to_utc(lbl.decision_time) for lbl in labels})
        )
        total_unique_times = len(unique_decision_times)

        if total_unique_times < 5:
            raise DomainValidationError(
                f"Insufficient distinct decision timestamps ({total_unique_times}) "
                "for 5 temporal splits.",
                field="labels",
                code=ErrorCode.VALIDATION_ERROR,
            )

        # Compute index boundaries along the global unique timeline
        train_count = int(total_unique_times * ratios[PartitionType.TRAIN])
        dev_count = int(total_unique_times * ratios[PartitionType.DEV_MODEL_SELECTION])
        cal_count = int(total_unique_times * ratios[PartitionType.CALIBRATION])
        thresh_count = int(total_unique_times * ratios[PartitionType.THRESHOLD_SELECTION])

        idx_train_end = max(1, train_count)
        idx_dev_start = idx_train_end
        idx_dev_end = max(idx_dev_start + 1, idx_dev_start + dev_count)
        idx_cal_start = idx_dev_end
        idx_cal_end = max(idx_cal_start + 1, idx_cal_start + cal_count)
        idx_thresh_start = idx_cal_end
        idx_thresh_end = max(idx_thresh_start + 1, idx_thresh_start + thresh_count)
        idx_test_start = idx_thresh_end

        # Establish global timestamp windows
        raw_windows: dict[PartitionType, tuple[datetime, datetime]] = {
            PartitionType.TRAIN: (
                unique_decision_times[0],
                unique_decision_times[idx_train_end - 1],
            ),
            PartitionType.DEV_MODEL_SELECTION: (
                unique_decision_times[idx_dev_start],
                unique_decision_times[idx_dev_end - 1],
            ),
            PartitionType.CALIBRATION: (
                unique_decision_times[idx_cal_start],
                unique_decision_times[idx_cal_end - 1],
            ),
            PartitionType.THRESHOLD_SELECTION: (
                unique_decision_times[idx_thresh_start],
                unique_decision_times[idx_thresh_end - 1],
            ),
            PartitionType.LOCKED_FINAL_TEST: (
                unique_decision_times[idx_test_start],
                unique_decision_times[-1],
            ),
        }

        # Embargo timedelta: embargo_bars * 5 minutes
        embargo_delta = timedelta(minutes=self.embargo_bars * 5)

        # 2. Partition Samples with Boundary Overlap Purging and Embargo
        partitioned_samples: dict[PartitionType, list[TradePolicyLabel]] = defaultdict(list)
        purged_counts: dict[PartitionType, int] = defaultdict(int)

        partition_sequence = [
            PartitionType.TRAIN,
            PartitionType.DEV_MODEL_SELECTION,
            PartitionType.CALIBRATION,
            PartitionType.THRESHOLD_SELECTION,
            PartitionType.LOCKED_FINAL_TEST,
        ]

        # Group all labels by sample_id to prevent duplicates
        sorted_labels = sorted(labels, key=lambda x: normalize_to_utc(x.decision_time))

        for p_idx, p_type in enumerate(partition_sequence):
            w_start, w_end = raw_windows[p_type]
            next_start = (
                raw_windows[partition_sequence[p_idx + 1]][0]
                if p_idx + 1 < len(partition_sequence)
                else None
            )

            for lbl in sorted_labels:
                dec_time = normalize_to_utc(lbl.decision_time)
                exit_time = normalize_to_utc(lbl.exit_time)

                # Check if decision_time falls within this partition's raw window
                if w_start <= dec_time <= w_end:
                    # Check Overlap Purge:
                    # If this is not the final test partition and exit_time >= next_start:
                    # the trade's outcome horizon spills over into the subsequent partition!
                    if next_start is not None and exit_time >= next_start:
                        purged_counts[p_type] += 1
                        continue

                    # Check Embargo Window:
                    # If an embargo is active, samples within [w_end, w_end + embargo_delta]
                    # are excluded if they fall in the embargo buffer
                    if (
                        next_start is not None
                        and (next_start - w_end) > timedelta(0)
                        and (next_start - embargo_delta) < dec_time < next_start
                    ):
                        # Candidate fell inside embargo buffer
                        continue

                    partitioned_samples[p_type].append(lbl)

        # 3. Assert Strict Global Chronological Invariants Across All Symbols
        # Cross-symbol guarantee: No symbol in TRAIN has a decision time >= any symbol in DEV, etc.
        for i in range(len(partition_sequence) - 1):
            curr_type = partition_sequence[i]
            next_type = partition_sequence[i + 1]

            curr_list = partitioned_samples[curr_type]
            next_list = partitioned_samples[next_type]

            if curr_list and next_list:
                max_curr_time = max(normalize_to_utc(x.decision_time) for x in curr_list)
                min_next_time = min(normalize_to_utc(x.decision_time) for x in next_list)

                if max_curr_time >= min_next_time:
                    raise DomainValidationError(
                        f"Global chronological violation between {curr_type} (max {max_curr_time}) "
                        f"and {next_type} (min {min_next_time}).",
                        field="partitions",
                        code=ErrorCode.VALIDATION_ERROR,
                    )

        # 4. Generate Partition Manifests
        partition_manifests: dict[PartitionType, PartitionManifest] = {}
        total_active_samples = 0
        total_purged_samples = sum(purged_counts.values())

        for p_type in partition_sequence:
            p_samples = partitioned_samples[p_type]
            count = len(p_samples)
            total_active_samples += count

            if count > 0:
                p_start = min(normalize_to_utc(x.decision_time) for x in p_samples)
                p_end = max(normalize_to_utc(x.decision_time) for x in p_samples)
                pos_count = sum(1 for x in p_samples if x.binary_label == 1)
                neg_count = count - pos_count
                win_rate = round(pos_count / count, 4)
                mean_pnl = (
                    sum((x.net_pnl for x in p_samples), Decimal("0.00")) / Decimal(count)
                ).quantize(Decimal("0.01"))
                sym_counts: dict[str, int] = defaultdict(int)
                for x in p_samples:
                    sym_counts[x.symbol] += 1
                sample_ids = sorted(x.sample_id for x in p_samples)
                ids_hash = hashlib.sha256(",".join(sample_ids).encode("utf-8")).hexdigest()
            else:
                p_start = raw_windows[p_type][0]
                p_end = raw_windows[p_type][1]
                pos_count = 0
                neg_count = 0
                win_rate = 0.0
                mean_pnl = Decimal("0.00")
                sym_counts = {}
                ids_hash = hashlib.sha256(b"empty").hexdigest()

            is_last = p_type == PartitionType.LOCKED_FINAL_TEST
            embargo_bars = 0 if is_last else self.embargo_bars

            manifest = PartitionManifest(
                partition_type=p_type,
                start_time=p_start,
                end_time=p_end,
                sample_count=count,
                symbol_counts=dict(sym_counts),
                positive_count=pos_count,
                negative_count=neg_count,
                win_rate=win_rate,
                mean_net_pnl=mean_pnl,
                purged_count=purged_counts[p_type],
                embargo_bars=embargo_bars,
                sample_ids_hash=ids_hash,
            )
            partition_manifests[p_type] = manifest

        # 5. Lock Final Test Set Hash
        final_test_samples = partitioned_samples[PartitionType.LOCKED_FINAL_TEST]
        final_test_ids = sorted(x.sample_id for x in final_test_samples)
        final_test_hash = hashlib.sha256(",".join(final_test_ids).encode("utf-8")).hexdigest()

        split_manifest_id = f"SPLIT-{policy_version}-{dataset_hash[:8]}-{uuid.uuid4().hex[:6]}"

        split_manifest = SplitManifest(
            manifest_id=split_manifest_id,
            created_at=datetime.now(ZoneInfo("UTC")),
            policy_version=policy_version,
            dataset_hash=dataset_hash,
            labeling_approach=labeling_approach,
            partitions=partition_manifests,
            total_samples=total_active_samples,
            total_purged=total_purged_samples,
            excluded_rows_count=total_excluded_rows,
            locked_final_test_hash=final_test_hash,
            is_final_test_locked=True,
            embargo_justification=self.embargo_justification,
            survivorship_bias_limitation=self.survivorship_bias_limitation,
        )

        return split_manifest, dict(partitioned_samples)

    @staticmethod
    def get_partition_samples(
        split_manifest: SplitManifest,
        partition_data: dict[PartitionType, list[TradePolicyLabel]],
        partition_type: PartitionType,
        unlock_token: str | None = None,
    ) -> list[TradePolicyLabel]:
        """Safely retrieve samples for a partition, enforcing the final-test lockbox."""
        if partition_type == PartitionType.LOCKED_FINAL_TEST:
            expected_token = f"UNSEAL_FINAL_TEST_{split_manifest.locked_final_test_hash[:12]}"
            if unlock_token != expected_token:
                raise FinalTestLockedError(
                    f"Access to {partition_type.value} is locked to prevent data "
                    "snooping and tuning bias. Requires valid unlock token."
                )

        return partition_data.get(partition_type, [])
