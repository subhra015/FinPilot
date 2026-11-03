"""Security and negative tests for market data importer (SEC-06/18/19/23, Layer 4)."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from finpilot.data import QuarantineManager, SafeDataImporter
from finpilot.schemas.errors import DomainValidationError


def test_path_traversal_prevention_in_filenames(tmp_path: Path) -> None:
    importer = SafeDataImporter(storage_dir=tmp_path)

    traversal_filenames = [
        "../../etc/passwd.csv",
        "..\\..\\Windows\\System32\\cmd.csv",
        "nested/../../secret.csv",
        "....//....//shell.csv",
        "\x00hidden.csv",
    ]

    for fname in traversal_filenames:
        clean = importer.sanitize_filename(fname)
        # Verify no path traversal markers or directory separators remain
        assert "/" not in clean
        assert "\\" not in clean
        assert ".." not in clean
        assert "\x00" not in clean
        assert clean.endswith(".csv")


def test_unsupported_and_archive_extensions_rejected(tmp_path: Path) -> None:
    importer = SafeDataImporter(storage_dir=tmp_path)

    bad_files = [
        ("archive.zip", b"PK\x03\x04some_zip_data"),
        ("archive.tar.gz", b"\x1f\x8bsome_gzip_data"),
        ("malicious.exe", b"MZ\x90\x00executable"),
        ("script.py", b"import os; os.system('calc')"),
        ("script.sh", b"#!/bin/bash\nrm -rf /"),
    ]

    for fname, payload in bad_files:
        with pytest.raises(DomainValidationError) as exc:
            importer.validate_file_content(fname, payload)
        assert "unsupported file format" in str(exc.value).lower()


def test_magic_byte_verification_for_parquet_and_csv(tmp_path: Path) -> None:
    importer = SafeDataImporter(storage_dir=tmp_path)

    # 1. Parquet missing PAR1 magic bytes
    fake_parquet = b"DATA_WITHOUT_PARQUET_MAGIC_BYTES"
    with pytest.raises(DomainValidationError) as exc_pq:
        importer.validate_file_content("test.parquet", fake_parquet)
    assert "magic bytes" in str(exc_pq.value).lower()

    # 2. CSV containing binary null bytes
    binary_csv = b"symbol,timestamp,open\x00,high,low,close,volume"
    with pytest.raises(DomainValidationError) as exc_null:
        importer.validate_file_content("test.csv", binary_csv)
    assert "binary null bytes" in str(exc_null.value).lower()

    # 3. Zip file disguised as a .csv extension
    disguised_zip = b"PK\x03\x04\x14\x00\x00\x00" + b"X" * 50
    with pytest.raises(DomainValidationError) as exc_zip:
        importer.validate_file_content("test.csv", disguised_zip)
    assert "archive files" in str(exc_zip.value).lower()


def test_file_size_limits_enforced(tmp_path: Path) -> None:
    # Set limit to 1000 bytes
    importer = SafeDataImporter(storage_dir=tmp_path, max_bytes=1000)

    # Empty file (0 bytes) rejected
    with pytest.raises(DomainValidationError) as exc_empty:
        importer.validate_file_content("empty.csv", b"")
    assert "empty" in str(exc_empty.value).lower()

    # Oversized file (> 1000 bytes) rejected
    oversized = b"a" * 1001
    with pytest.raises(DomainValidationError) as exc_large:
        importer.validate_file_content("large.csv", oversized)
    assert "exceeds maximum allowed size" in str(exc_large.value).lower()


def test_csv_schema_and_column_bounds_enforced(tmp_path: Path) -> None:
    importer = SafeDataImporter(storage_dir=tmp_path)

    # Missing mandatory columns (missing 'volume' and 'high')
    incomplete_csv = (
        b"symbol,timestamp,open,low,close\nRELIANCE,2026-10-30T09:15:00+00:00,2500,2490,2510\n"
    )
    with pytest.raises(DomainValidationError) as exc_missing:
        importer.import_file("test.csv", incomplete_csv)
    assert "missing mandatory columns" in str(exc_missing.value).lower()

    # Excessive columns (> 20)
    extra_cols = ",".join([f"extra_{i}" for i in range(25)])
    excessive_csv = f"symbol,timestamp,open,high,low,close,volume,{extra_cols}\n".encode()
    with pytest.raises(DomainValidationError) as exc_cols:
        importer.import_file("test.csv", excessive_csv)
    assert "maximum column limit" in str(exc_cols.value).lower()


def test_valid_csv_import_with_quarantine_routing(tmp_path: Path) -> None:
    qm = QuarantineManager(quarantine_dir=tmp_path / "quarantine")
    importer = SafeDataImporter(storage_dir=tmp_path / "imports", quarantine_manager=qm)

    csv_data = """symbol,timestamp,open,high,low,close,volume
RELIANCE,2026-10-30T03:45:00+00:00,2500.0,2520.0,2495.0,2510.0,15000
RELIANCE,2026-10-30T03:50:00+00:00,2510.0,2500.0,2500.0,2505.0,12000
UNKNOWN_CO,2026-10-30T03:55:00+00:00,100.0,110.0,90.0,105.0,5000
TCS,2026-10-30T03:45:00+00:00,3800.0,3830.0,3790.0,3820.0,8000
"""
    result, valid_records = importer.import_file("market_data.csv", csv_data.encode())

    # Row 1 is valid (RELIANCE)
    # Row 2 is invalid (High 2500 < Open 2510) -> quarantined
    # Row 3 is invalid (UNKNOWN_CO not in known registry) -> quarantined
    # Row 4 is valid (TCS)
    assert result.row_count == 4
    assert result.valid_count == 2
    assert result.quarantine_count == 2
    assert len(valid_records) == 2
    assert "RELIANCE" in result.symbols
    assert "TCS" in result.symbols
    assert len(qm.get_records()) == 2


def test_valid_parquet_import(tmp_path: Path) -> None:
    importer = SafeDataImporter(storage_dir=tmp_path / "imports")

    parquet_file = tmp_path / "sample.parquet"
    data = {
        "symbol": ["RELIANCE", "TCS"],
        "timestamp": ["2026-10-30T03:45:00+00:00", "2026-10-30T03:45:00+00:00"],
        "open": ["2500.0", "3800.0"],
        "high": ["2520.0", "3830.0"],
        "low": ["2490.0", "3790.0"],
        "close": ["2510.0", "3820.0"],
        "volume": [10000, 5000],
    }
    table = pa.Table.from_pydict(data)
    pq.write_table(table, parquet_file)

    result, records = importer.import_file("sample.parquet", parquet_file.read_bytes())
    assert result.row_count == 2
    assert result.valid_count == 2
    assert result.quarantine_count == 0
    assert len(records) == 2
