"""Tests for final-test lockbox and anti-snooping controls (Layer 8).

Governed by:
- ACCEPTANCE_GATES.md §1 (G-8, Unseen data)
- DATA_AND_PERFORMANCE_POLICY.md §7 (Evaluation Hygiene)
- Layer 8 Gate: Lock final-test identifiers and prevent routine tuning code
  from loading final-test labels/results.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from finpilot.labeling.lockbox import FinalTestLockbox
from finpilot.labeling.models import (
    LabelingApproach,
    PartitionType,
    TradeOutcomeReason,
    TradePolicyLabel,
)
from finpilot.labeling.split_manager import FinalTestLockedError, TemporalSplitManager
from finpilot.schemas.errors import DomainValidationError

IST = ZoneInfo("Asia/Kolkata")


def make_label(
    symbol: str,
    ts_ist: datetime,
    net_pnl: float = 10.0,
    instrument_id: int = 1,
    holding_bars: int = 1,
) -> TradePolicyLabel:
    """Helper creating a TradePolicyLabel."""
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
        entry_price=Decimal("100.00"),
        exit_price=Decimal("101.50") if net_pnl > 0 else Decimal("98.50"),
        quantity=10,
        gross_pnl=pnl + Decimal("2.00"),
        fees=Decimal("2.00"),
        net_pnl=pnl,
        gross_return=Decimal("0.0150"),
        net_return=Decimal("0.0100"),
        binary_label=1 if net_pnl > 0 else 0,
        outcome_reason=TradeOutcomeReason.TARGET_HIT,
        is_ambiguous_exit=False,
        is_gap_fill=False,
        pit_universe_eligible=True,
        features={"ret_1": 0.001, "sma_ratio_9_21": 0.002},
        policy_version="TP-V1",
        labeling_approach=LabelingApproach.APPROACH_A_SHARED_SIZING,
    )


def test_locked_final_test_routine_access_blocked() -> None:
    """Verify that routine access without token raises FinalTestLockedError."""
    split_mgr = TemporalSplitManager(embargo_bars=0)
    base_time = datetime(2026, 1, 5, 9, 30, tzinfo=IST)
    labels = [make_label("RELIANCE", base_time + timedelta(minutes=5 * i)) for i in range(25)]

    manifest, partitioned = split_mgr.create_splits(labels, dataset_hash="test_lockbox")
    lockbox = FinalTestLockbox(manifest, partitioned)

    assert lockbox.is_locked is True

    # 1. Access without token must raise FinalTestLockedError
    with pytest.raises(FinalTestLockedError, match="Access to LOCKED_FINAL_TEST is blocked"):
        lockbox.get_final_test_samples()

    # 2. Access with invalid token must also raise FinalTestLockedError
    with pytest.raises(FinalTestLockedError, match="Access to LOCKED_FINAL_TEST is blocked"):
        lockbox.get_final_test_samples(unlock_token="INVALID_TOKEN_123")  # noqa: S106


def test_locked_final_test_unseal_with_valid_token() -> None:
    """Verify that providing the valid unseal token returns final test samples."""
    split_mgr = TemporalSplitManager(embargo_bars=0)
    base_time = datetime(2026, 1, 5, 9, 30, tzinfo=IST)
    labels = [make_label("TCS", base_time + timedelta(minutes=5 * i)) for i in range(25)]

    manifest, partitioned = split_mgr.create_splits(labels, dataset_hash="test_unseal")
    lockbox = FinalTestLockbox(manifest, partitioned)

    token = lockbox.generate_unlock_token()
    assert token.startswith("UNSEAL_FINAL_TEST_")

    # Unseal with valid token succeeds
    test_samples = lockbox.get_final_test_samples(unlock_token=token)
    assert len(test_samples) > 0
    assert lockbox.verify_integrity(test_samples) is True


def test_routine_partitions_accessible_without_token() -> None:
    """Verify that TRAIN, DEV, CALIBRATION, and THRESHOLD are accessible without token."""
    split_mgr = TemporalSplitManager(embargo_bars=0)
    base_time = datetime(2026, 1, 5, 9, 30, tzinfo=IST)
    labels = [make_label("INFY", base_time + timedelta(minutes=5 * i)) for i in range(50)]

    manifest, partitioned = split_mgr.create_splits(labels, dataset_hash="test_routine")
    lockbox = FinalTestLockbox(manifest, partitioned)

    # All routine tuning partitions are freely accessible
    assert len(lockbox.get_train_samples()) > 0
    assert len(lockbox.get_dev_samples()) > 0
    assert len(lockbox.get_calibration_samples()) > 0
    assert len(lockbox.get_threshold_samples()) > 0


def test_tamper_detection_fails_on_mutation() -> None:
    """Verify that tampering with test set sample IDs fails cryptographic verification."""
    split_mgr = TemporalSplitManager(embargo_bars=0)
    base_time = datetime(2026, 1, 5, 9, 30, tzinfo=IST)
    labels = [make_label("HDFCBANK", base_time + timedelta(minutes=5 * i)) for i in range(25)]

    manifest, partitioned = split_mgr.create_splits(labels, dataset_hash="test_tamper")
    lockbox = FinalTestLockbox(manifest, partitioned)

    # Tamper with the internal test partition samples
    tampered_samples = list(partitioned[PartitionType.LOCKED_FINAL_TEST])
    # Replace a sample with an injected foreign sample
    tampered_samples[0] = make_label("HDFCBANK", datetime(2025, 1, 1, 10, 0, tzinfo=IST))

    # Direct integrity verification with tampered samples must fail
    with pytest.raises(DomainValidationError, match="Integrity check failed"):
        lockbox.verify_integrity(tampered_samples)


def test_lockbox_save_and_manifest_roundtrip(tmp_path: Path) -> None:
    """Verify that split manifest saves to disk and contains full audit provenance."""
    split_mgr = TemporalSplitManager(embargo_bars=12)
    base_time = datetime(2026, 1, 5, 9, 30, tzinfo=IST)
    labels = [make_label("SBIN", base_time + timedelta(minutes=5 * i)) for i in range(30)]

    manifest, partitioned = split_mgr.create_splits(labels, dataset_hash="roundtrip_hash")
    lockbox = FinalTestLockbox(manifest, partitioned)

    save_path = tmp_path / "splits" / "test_manifest.json"
    lockbox.save_manifest(save_path)

    assert save_path.exists()
    with open(save_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["manifest_id"] == manifest.manifest_id
    assert data["is_final_test_locked"] is True
    assert data["locked_final_test_hash"] == manifest.locked_final_test_hash
    assert "partitions" in data
    assert len(data["partitions"]) == 5
