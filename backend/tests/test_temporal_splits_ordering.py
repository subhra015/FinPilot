"""Tests for globally chronological partitions and split manifests (Layer 8).

Governed by:
- DATA_AND_PERFORMANCE_POLICY.md §7, §8
- Layer 8 Gate: Globally chronological ordering across all symbols, no symbol
  contributing later dates to training while earlier dates are held out,
  and deterministic split manifests.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from finpilot.labeling.models import (
    LabelingApproach,
    PartitionType,
    TradeOutcomeReason,
    TradePolicyLabel,
)
from finpilot.labeling.split_manager import TemporalSplitManager
from finpilot.schemas.errors import DomainValidationError

IST = ZoneInfo("Asia/Kolkata")


def make_label(
    symbol: str,
    ts_ist: datetime,
    holding_bars: int = 3,
    net_pnl: float = 15.0,
    instrument_id: int = 1,
) -> TradePolicyLabel:
    """Helper creating a valid TradePolicyLabel."""
    utc_dec = ts_ist.astimezone(ZoneInfo("UTC"))
    utc_entry = utc_dec + timedelta(minutes=5)
    utc_exit = utc_entry + timedelta(minutes=holding_bars * 5)
    pnl = Decimal(str(net_pnl))
    return TradePolicyLabel(
        sample_id=f"LBL-{instrument_id}-{utc_dec.strftime('%Y%m%d%H%M')}",
        instrument_id=instrument_id,
        symbol=symbol,
        decision_time=utc_dec,
        entry_time=utc_entry,
        exit_time=utc_exit,
        holding_bars=holding_bars,
        entry_price=Decimal("1000.00"),
        exit_price=Decimal("1015.00") if net_pnl > 0 else Decimal("985.00"),
        quantity=10,
        gross_pnl=pnl + Decimal("5.00"),
        fees=Decimal("5.00"),
        net_pnl=pnl,
        gross_return=Decimal("0.0020"),
        net_return=Decimal("0.0015"),
        binary_label=1 if net_pnl > 0 else 0,
        outcome_reason=(
            TradeOutcomeReason.TARGET_HIT
            if net_pnl > 0
            else TradeOutcomeReason.STOP_LOSS_HIT
        ),
        is_ambiguous_exit=False,
        is_gap_fill=False,
        pit_universe_eligible=True,
        features={"ret_1": 0.002, "sma_ratio_9_21": 0.005},
        policy_version="TP-V1",
        labeling_approach=LabelingApproach.APPROACH_A_SHARED_SIZING,
    )


def test_global_chronological_ordering() -> None:
    """Verify that all 5 partitions are strictly chronological."""
    split_mgr = TemporalSplitManager(embargo_bars=0)  # No embargo in this test to check raw windows

    base_time = datetime(2026, 1, 5, 10, 0, tzinfo=IST)
    labels = []
    # Create 50 candles over time
    for i in range(50):
        t = base_time + timedelta(minutes=5 * i)
        labels.append(make_label("RELIANCE", t, net_pnl=10.0 if i % 2 == 0 else -10.0))

    manifest, partitioned = split_mgr.create_splits(
        labels=labels,
        dataset_hash="a" * 64,
        policy_version="TP-V1",
    )

    sequence = [
        PartitionType.TRAIN,
        PartitionType.DEV_MODEL_SELECTION,
        PartitionType.CALIBRATION,
        PartitionType.THRESHOLD_SELECTION,
        PartitionType.LOCKED_FINAL_TEST,
    ]

    for i in range(len(sequence) - 1):
        curr_p = sequence[i]
        next_p = sequence[i + 1]

        curr_samples = partitioned[curr_p]
        next_samples = partitioned[next_p]

        assert len(curr_samples) > 0
        assert len(next_samples) > 0

        max_curr = max(s.decision_time for s in curr_samples)
        min_next = min(s.decision_time for s in next_samples)

        # Global chronological ordering strictly asserted
        assert max_curr < min_next


def test_cross_symbol_chronological_invariant() -> None:
    """Verify multi-symbol invariant: No symbol in TRAIN is dated after other symbol's DEV/TEST."""
    split_mgr = TemporalSplitManager(embargo_bars=0)

    base_time = datetime(2026, 1, 5, 9, 30, tzinfo=IST)
    labels = []
    # Create 3 symbols interleaved along identical timeline
    symbols = [("RELIANCE", 1), ("TCS", 2), ("INFY", 3)]
    for i in range(40):
        t = base_time + timedelta(minutes=5 * i)
        for sym, inst_id in symbols:
            labels.append(make_label(sym, t, instrument_id=inst_id))

    manifest, partitioned = split_mgr.create_splits(
        labels=labels,
        dataset_hash="b" * 64,
        policy_version="TP-V1",
    )

    train_samples = partitioned[PartitionType.TRAIN]
    dev_samples = partitioned[PartitionType.DEV_MODEL_SELECTION]
    test_samples = partitioned[PartitionType.LOCKED_FINAL_TEST]

    # Every symbol in train must be strictly earlier than any symbol in dev
    max_train_time = max(s.decision_time for s in train_samples)
    min_dev_time = min(s.decision_time for s in dev_samples)
    min_test_time = min(s.decision_time for s in test_samples)

    assert max_train_time < min_dev_time < min_test_time

    # Verify per-symbol breakdown in manifests
    train_manifest = manifest.partitions[PartitionType.TRAIN]
    assert set(train_manifest.symbol_counts.keys()) == {"RELIANCE", "TCS", "INFY"}


def test_split_manifest_determinism_and_hashing() -> None:
    """Verify splitting identical labels produces identical manifests and hashes."""
    split_mgr = TemporalSplitManager(embargo_bars=12)

    base_time = datetime(2026, 1, 5, 10, 0, tzinfo=IST)
    labels = [
        make_label("RELIANCE", base_time + timedelta(minutes=5 * i), net_pnl=float(i % 5))
        for i in range(30)
    ]

    manifest1, _ = split_mgr.create_splits(labels, dataset_hash="hash123")
    manifest2, _ = split_mgr.create_splits(labels, dataset_hash="hash123")

    assert manifest1.locked_final_test_hash == manifest2.locked_final_test_hash
    assert manifest1.total_samples == manifest2.total_samples
    assert manifest1.total_purged == manifest2.total_purged


def test_insufficient_timestamps_rejected() -> None:
    """Verify that fewer than 5 timestamps raises DomainValidationError."""
    split_mgr = TemporalSplitManager()
    base_time = datetime(2026, 1, 5, 10, 0, tzinfo=IST)
    labels = [make_label("RELIANCE", base_time + timedelta(minutes=5 * i)) for i in range(3)]

    with pytest.raises(DomainValidationError, match="Insufficient distinct decision timestamps"):
        split_mgr.create_splits(labels, dataset_hash="short_dataset")
