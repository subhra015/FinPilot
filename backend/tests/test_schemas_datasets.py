"""Dataset manifest and provider metadata validation tests (Layer 3)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from finpilot.db.enums import DataMode
from finpilot.schemas import (
    DatasetManifestCreate,
    DomainValidationError,
)


def test_valid_dataset_manifest_and_metadata() -> None:
    now = datetime.now(UTC)
    content = b"sample_parquet_bytes"
    checksum = hashlib.sha256(content).hexdigest()

    manifest = DatasetManifestCreate(
        dataset_name="nse_cash_5m_completed",
        dataset_version="v1.0.0",
        mode=DataMode.HISTORICAL_REPLAY,
        provider_source="NSE_BHAVCOPY_VERIFIED",
        file_path_or_uri="data/parquet/nse_5m.parquet",
        sha256_checksum=checksum,
        row_count=50000,
        start_timestamp=now,
        end_timestamp=now,
        schema_version="parquet_arrow_v1",
    )
    assert manifest.dataset_name == "nse_cash_5m_completed"
    assert manifest.sha256_checksum == checksum
    assert manifest.row_count == 50000


@pytest.mark.parametrize(
    "bad_checksum",
    [
        "a" * 63,  # 63 chars (too short)
        "a" * 65,  # 65 chars (too long)
        "g" * 64,  # Non-hex character 'g'
        "A" * 64,  # Uppercase not permitted
        "",
    ],
)
def test_invalid_sha256_checksum_rejected(bad_checksum: str) -> None:
    now = datetime.now(UTC)
    with pytest.raises((DomainValidationError, ValidationError)) as exc:
        DatasetManifestCreate(
            dataset_name="test_data",
            dataset_version="v1",
            provider_source="TEST",
            file_path_or_uri="test.parquet",
            sha256_checksum=bad_checksum,
            row_count=100,
            start_timestamp=now,
            end_timestamp=now,
            schema_version="v1",
        )
    assert any(
        token in str(exc.value).lower() for token in ("sha-256", "sha256", "checksum", "character")
    )


def test_inverted_manifest_timestamps_rejected() -> None:
    t_start = datetime(2026, 10, 31, 15, 30, tzinfo=UTC)
    t_end = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)  # Earlier than start

    with pytest.raises((DomainValidationError, ValidationError)) as exc:
        DatasetManifestCreate(
            dataset_name="test_data",
            dataset_version="v1",
            provider_source="TEST",
            file_path_or_uri="test.parquet",
            sha256_checksum="a" * 64,
            row_count=100,
            start_timestamp=t_start,
            end_timestamp=t_end,
            schema_version="v1",
        )
    assert "start_timestamp" in str(exc.value).lower()


def test_negative_row_count_rejected() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        DatasetManifestCreate(
            dataset_name="test_data",
            dataset_version="v1",
            provider_source="TEST",
            file_path_or_uri="test.parquet",
            sha256_checksum="a" * 64,
            row_count=-5,
            start_timestamp=now,
            end_timestamp=now,
            schema_version="v1",
        )
