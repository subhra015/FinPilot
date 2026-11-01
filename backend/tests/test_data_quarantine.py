"""Quarantine subsystem and audit trail tests (Layer 4)."""

from __future__ import annotations

import json
from pathlib import Path

from finpilot.data import QuarantineManager


def test_quarantine_row_and_manifest_generation(tmp_path: Path) -> None:
    qm = QuarantineManager(quarantine_dir=tmp_path)

    # 1. Quarantine an invalid row
    rec = qm.quarantine_row(
        source="TEST_SOURCE",
        rejection_reason="OHLC High less than Open",
        raw_payload='{"open": 2550, "high": 2500, "symbol": "RELIANCE"}',
        symbol="RELIANCE",
    )
    assert rec.rejection_reason == "OHLC High less than Open"
    assert rec.symbol == "RELIANCE"
    assert len(qm.get_records()) == 1

    # 2. Quarantine an invalid file
    bad_file = tmp_path / "corrupt.parquet"
    bad_file.write_bytes(b"NOT_A_VALID_PARQUET_FILE")
    f_rec = qm.quarantine_file(
        file_path=bad_file,
        rejection_reason="Corrupt magic bytes",
        source="TEST_IMPORTER",
    )
    assert "Corrupt magic bytes" in f_rec.rejection_reason
    assert len(qm.get_records()) == 2

    # 3. Write manifest
    manifest_path = qm.write_manifest(output_dir=tmp_path)
    assert manifest_path.exists()

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_data["quarantined_count"] == 2
    assert len(manifest_data["records"]) == 2
    assert manifest_data["records"][0]["symbol"] == "RELIANCE"

    # 4. Clear memory
    qm.clear()
    assert len(qm.get_records()) == 0
