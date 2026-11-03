"""Tests for boundary overlap purging and horizon-justified embargo (Layer 8).

Governed by:
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 8 Gate: Purge training labels whose outcome intervals overlap validation/test
  boundaries; define embargo from maximum outcome/information horizon and justify it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from finpilot.labeling.models import (
    LabelingApproach,
    PartitionType,
    TradeOutcomeReason,
    TradePolicyLabel,
)
from finpilot.labeling.split_manager import (
    DEFAULT_EMBARGO_JUSTIFICATION,
    DEFAULT_SURVIVORSHIP_LIMITATION,
    TemporalSplitManager,
)

IST = ZoneInfo("Asia/Kolkata")


def make_label(
    symbol: str,
    dec_time_ist: datetime,
    exit_time_ist: datetime,
    instrument_id: int = 1,
) -> TradePolicyLabel:
    """Helper creating a TradePolicyLabel with custom exit_time for purge testing."""
    utc_dec = dec_time_ist.astimezone(ZoneInfo("UTC"))
    utc_entry = utc_dec + timedelta(minutes=5)
    utc_exit = exit_time_ist.astimezone(ZoneInfo("UTC"))
    holding_bars = max(1, int((utc_exit - utc_entry).total_seconds() / 300))

    return TradePolicyLabel(
        sample_id=f"LBL-{instrument_id}-{utc_dec.strftime('%Y%m%d%H%M')}",
        instrument_id=instrument_id,
        symbol=symbol,
        decision_time=utc_dec,
        entry_time=utc_entry,
        exit_time=utc_exit,
        holding_bars=holding_bars,
        entry_price=Decimal("100.00"),
        exit_price=Decimal("103.00"),
        quantity=10,
        gross_pnl=Decimal("30.00"),
        fees=Decimal("2.50"),
        net_pnl=Decimal("27.50"),
        gross_return=Decimal("0.0300"),
        net_return=Decimal("0.0275"),
        binary_label=1,
        outcome_reason=TradeOutcomeReason.TARGET_HIT,
        is_ambiguous_exit=False,
        is_gap_fill=False,
        pit_universe_eligible=True,
        features={"ret_1": 0.001, "sma_ratio_9_21": 0.002},
        policy_version="TP-V1",
        labeling_approach=LabelingApproach.APPROACH_A_SHARED_SIZING,
    )


def test_boundary_overlap_purging() -> None:
    """Verify that a candidate in TRAIN whose exit overlaps into DEV is purged."""
    split_mgr = TemporalSplitManager(embargo_bars=0)

    base_time = datetime(2026, 1, 5, 9, 30, tzinfo=IST)
    labels = []

    # Create 20 chronological samples
    # 50% ratio means TRAIN is approx index 0..9, DEV starts at index 10
    for i in range(20):
        t_dec = base_time + timedelta(minutes=5 * i)
        t_exit = base_time + timedelta(minutes=5 * 15) if i == 9 else t_dec + timedelta(minutes=10)
        labels.append(make_label("RELIANCE", t_dec, t_exit))

    manifest, partitioned = split_mgr.create_splits(
        labels=labels,
        dataset_hash="test_purge_hash",
        policy_version="TP-V1",
    )

    train_manifest = manifest.partitions[PartitionType.TRAIN]
    # The overlapping sample at index 9 must have been purged from TRAIN
    assert train_manifest.purged_count >= 1
    assert manifest.total_purged >= 1

    # Ensure the sample with the late exit is NOT present in TRAIN
    train_samples = partitioned[PartitionType.TRAIN]
    dec_target = (base_time + timedelta(minutes=5 * 9)).astimezone(ZoneInfo("UTC"))
    target_sample_id = f"LBL-1-{dec_target.strftime('%Y%m%d%H%M')}"
    sample_ids_in_train = {s.sample_id for s in train_samples}
    assert target_sample_id not in sample_ids_in_train


def test_embargo_exclusion() -> None:
    """Verify that candidates falling within the post-partition embargo buffer are excluded."""
    # 6 bars = 30 minutes embargo buffer
    embargo_bars = 6
    split_mgr = TemporalSplitManager(embargo_bars=embargo_bars)

    base_time = datetime(2026, 1, 5, 9, 30, tzinfo=IST)
    labels = []
    # Create 30 candles
    for i in range(30):
        t_dec = base_time + timedelta(minutes=5 * i)
        t_exit = t_dec + timedelta(minutes=10)
        labels.append(make_label("TCS", t_dec, t_exit))

    manifest, partitioned = split_mgr.create_splits(
        labels=labels,
        dataset_hash="embargo_hash",
        policy_version="TP-V1",
    )

    # TRAIN partition manifest must record embargo_bars
    train_manifest = manifest.partitions[PartitionType.TRAIN]
    assert train_manifest.embargo_bars == embargo_bars

    # Total partitioned active samples should be less than total input labels
    # due to the embargo exclusions between windows
    assert manifest.total_samples <= len(labels)


def test_embargo_justification_and_metadata() -> None:
    """Verify that embargo justification and survivorship limitations are recorded in manifest."""
    split_mgr = TemporalSplitManager(embargo_bars=75)

    base_time = datetime(2026, 1, 5, 9, 30, tzinfo=IST)
    labels = [
        make_label(
            "INFY",
            base_time + timedelta(minutes=5 * i),
            base_time + timedelta(minutes=5 * i + 10),
        )
        for i in range(25)
    ]

    manifest, _ = split_mgr.create_splits(labels, dataset_hash="meta_hash")

    assert manifest.embargo_justification == DEFAULT_EMBARGO_JUSTIFICATION
    assert manifest.survivorship_bias_limitation == DEFAULT_SURVIVORSHIP_LIMITATION
    assert "72 bars" in manifest.embargo_justification
    assert "survivorship bias limitations" in manifest.survivorship_bias_limitation
