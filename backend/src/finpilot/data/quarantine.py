"""Quarantine subsystem for invalid market data rows and files (Layer 4).

Enforces the policy: never silently repair data without recording the transformation.
Stores quarantined entries with reason, raw payload, timestamp, and audit trail.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from .models import QuarantinedRecord


class QuarantineManager:
    """Manages quarantine storage and manifest generation for corrupt or rejected data."""

    def __init__(self, quarantine_dir: Path | str = "data/quarantine") -> None:
        self._dir = Path(quarantine_dir)
        self._records: list[QuarantinedRecord] = []

    @property
    def quarantine_directory(self) -> Path:
        return self._dir

    def quarantine_row(
        self,
        source: str,
        rejection_reason: str,
        raw_payload: str,
        symbol: str | None = None,
        timestamp: datetime | None = None,
    ) -> QuarantinedRecord:
        """Quarantine an invalid data row with reason and raw payload."""
        rec = QuarantinedRecord(
            source=source,
            quarantined_at=datetime.now(UTC),
            rejection_reason=rejection_reason,
            raw_payload=raw_payload,
            symbol=symbol,
            timestamp=timestamp,
        )
        self._records.append(rec)
        return rec

    def quarantine_file(
        self,
        file_path: Path | str,
        rejection_reason: str,
        source: str,
    ) -> QuarantinedRecord:
        """Quarantine an invalid or corrupted file."""
        p = Path(file_path)
        content_bytes = p.read_bytes() if p.exists() else b""
        file_hash = hashlib.sha256(content_bytes).hexdigest()

        rec = QuarantinedRecord(
            source=source,
            quarantined_at=datetime.now(UTC),
            rejection_reason=f"{rejection_reason} (file: {p.name}, sha256: {file_hash})",
            raw_payload=f"PATH:{p.as_posix()};BYTES:{len(content_bytes)};SHA256:{file_hash}",
        )
        self._records.append(rec)
        return rec

    def get_records(self) -> Sequence[QuarantinedRecord]:
        """Return all quarantined records in memory."""
        return list(self._records)

    def write_manifest(self, output_dir: Path | str | None = None) -> Path:
        """Write a quarantine manifest JSON file with SHA-256 integrity hash."""
        target_dir = Path(output_dir) if output_dir else self._dir
        target_dir.mkdir(parents=True, exist_ok=True)

        manifest_data = {
            "quarantined_count": len(self._records),
            "generated_at": datetime.now(UTC).isoformat(),
            "records": [r.model_dump(mode="json") for r in self._records],
        }

        manifest_json = json.dumps(manifest_data, indent=2)
        manifest_hash = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()

        manifest_file = target_dir / f"quarantine_manifest_{manifest_hash[:16]}.json"
        manifest_file.write_text(manifest_json, encoding="utf-8")
        return manifest_file

    def clear(self) -> None:
        """Clear the in-memory quarantine records."""
        self._records.clear()
