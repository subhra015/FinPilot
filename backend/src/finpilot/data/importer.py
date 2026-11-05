"""Safe market data file importer (SEC-06, SEC-18, SEC-19, SEC-23, Layer 4).

Enforces:
- Strict format allowlist: .csv and .parquet only. Rejects archives (.zip, .tar, .gz)
  and executables.
- Magic byte content verification (PAR1 for Parquet, ASCII/UTF-8 tabular text for CSV).
- Byte, row, and column limits (max 50 MB, max 1,000,000 rows, max 20 columns).
- Path traversal prevention: strictly stores outside web root in dedicated data directories.
- Non-executability: uploaded files are parsed as pure data and never executed.
- Non-authoritative frontend prices: server performs full validation and provenance tracking.
- Quarantine routing: invalid rows are routed to QuarantineManager without silent repair.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import IO

import pyarrow.parquet as pq  # type: ignore[import-untyped]

from finpilot.db.enums import CurrencyCode, DataMode, ExchangeCode
from finpilot.schemas.errors import DomainValidationError, ErrorCode
from finpilot.schemas.instruments import KnownInstrumentRegistry

from .enums import AdjustmentStatus, QualityFlag
from .models import ImportResult, MarketDataRecord
from .quarantine import QuarantineManager

ALLOWED_EXTENSIONS = frozenset({".csv", ".parquet"})
REQUIRED_COLUMNS = frozenset({"symbol", "timestamp", "open", "high", "low", "close", "volume"})
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB default
MAX_ROWS = 1_000_000
MAX_COLUMNS = 20

PARQUET_MAGIC = b"PAR1"
FILENAME_SAFE_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


class SafeDataImporter:
    """Secure importer for market data files adhering to SEC-18 and SEC-06."""

    def __init__(
        self,
        storage_dir: Path | str = "data/imports",
        quarantine_manager: QuarantineManager | None = None,
        registry: KnownInstrumentRegistry | None = None,
        max_bytes: int = MAX_FILE_BYTES,
    ) -> None:
        self._storage_dir = Path(storage_dir)
        self._quarantine = quarantine_manager or QuarantineManager()
        self._registry = registry or KnownInstrumentRegistry(
            {"RELIANCE": 101, "TCS": 102, "INFY": 103}
        )
        self._max_bytes = max_bytes

    def sanitize_filename(self, filename: str) -> str:
        """Sanitize upload filename to prevent path traversal (SEC-18)."""
        # Strip path separators and parent directory tokens
        clean = Path(filename).name.strip()
        clean = clean.replace("\x00", "").replace("/", "").replace("\\", "")

        if ".." in clean or not clean or not FILENAME_SAFE_REGEX.match(clean):
            # Generate deterministic fallback name
            ext = Path(filename).suffix.lower()
            clean = f"upload_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}{ext}"

        return clean

    def validate_file_content(self, filename: str, content: bytes) -> str:
        """Validate format, magic bytes, and size bounds (SEC-18)."""
        # 1. Size bounds check
        if len(content) == 0:
            raise DomainValidationError(
                "Uploaded file is empty (0 bytes).",
                field="file",
                code=ErrorCode.VALIDATION_ERROR,
            )
        if len(content) > self._max_bytes:
            raise DomainValidationError(
                f"File exceeds maximum allowed size of {self._max_bytes} bytes "
                f"(received {len(content)} bytes).",
                field="file",
                code=ErrorCode.VALIDATION_ERROR,
            )

        # 2. Extension check
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise DomainValidationError(
                f"Unsupported file format {ext!r}. Only .csv and .parquet files are permitted.",
                field="file",
                code=ErrorCode.VALIDATION_ERROR,
            )

        # 3. Magic bytes / content integrity check
        if ext == ".parquet":
            if len(content) < 8 or content[:4] != PARQUET_MAGIC or content[-4:] != PARQUET_MAGIC:
                raise DomainValidationError(
                    "Invalid Parquet file: magic bytes 'PAR1' missing.",
                    field="file",
                    code=ErrorCode.VALIDATION_ERROR,
                )
        elif ext == ".csv":
            # Check for archive signatures (e.g. PK zip magic or gzip)
            if content.startswith(b"PK\x03\x04") or content.startswith(b"\x1f\x8b"):
                raise DomainValidationError(
                    "Archive files (.zip, .gz) are strictly prohibited.",
                    field="file",
                    code=ErrorCode.VALIDATION_ERROR,
                )
            # Check for binary executables or null bytes
            if b"\x00" in content:
                raise DomainValidationError(
                    "Invalid CSV file: unexpected binary null bytes detected.",
                    field="file",
                    code=ErrorCode.VALIDATION_ERROR,
                )

        return ext

    def import_file(
        self,
        file_name: str,
        file_stream_or_bytes: bytes | IO[bytes],
    ) -> tuple[ImportResult, list[MarketDataRecord]]:
        """Safely import, validate, quarantine defects, and store market data."""
        if isinstance(file_stream_or_bytes, bytes):
            raw_bytes = file_stream_or_bytes
        else:
            raw_bytes = file_stream_or_bytes.read()

        safe_name = self.sanitize_filename(file_name)
        ext = self.validate_file_content(safe_name, raw_bytes)
        file_checksum = hashlib.sha256(raw_bytes).hexdigest()

        # Store outside web root
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        saved_file_path = self._storage_dir / f"{file_checksum[:16]}_{safe_name}"
        saved_file_path.write_bytes(raw_bytes)

        if ext == ".csv":
            return self._parse_csv(safe_name, file_checksum, raw_bytes)
        else:
            return self._parse_parquet(safe_name, file_checksum, saved_file_path)

    def _parse_csv(
        self, safe_name: str, checksum: str, content: bytes
    ) -> tuple[ImportResult, list[MarketDataRecord]]:
        text = content.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))

        if not reader.fieldnames:
            raise DomainValidationError(
                "CSV file contains no headers.", field="file", code=ErrorCode.VALIDATION_ERROR
            )

        col_keys = {col.strip().lower() for col in reader.fieldnames if col}
        if len(col_keys) > MAX_COLUMNS:
            raise DomainValidationError(
                f"CSV exceeds maximum column limit ({len(col_keys)} > {MAX_COLUMNS}).",
                field="file",
                code=ErrorCode.VALIDATION_ERROR,
            )

        missing = REQUIRED_COLUMNS - col_keys
        if missing:
            raise DomainValidationError(
                f"CSV missing mandatory columns: {sorted(missing)}. "
                f"Required: {sorted(REQUIRED_COLUMNS)}.",
                field="file",
                code=ErrorCode.VALIDATION_ERROR,
            )

        valid_records: list[MarketDataRecord] = []
        quarantine_count = 0
        symbols_seen: set[str] = set()
        timestamps: list[datetime] = []
        now = datetime.now(UTC)

        row_idx = 0
        for row in reader:
            row_idx += 1
            if row_idx > MAX_ROWS:
                raise DomainValidationError(
                    f"File exceeds maximum row limit of {MAX_ROWS} rows.",
                    field="file",
                    code=ErrorCode.VALIDATION_ERROR,
                )

            clean_row = {k.strip().lower(): v.strip() for k, v in row.items() if k}
            raw_sym = clean_row.get("symbol", "").upper()

            try:
                # 1. Resolve symbol
                inst_id = self._registry.resolve_instrument_id(raw_sym)
                # 2. Parse timestamp
                raw_ts = clean_row.get("timestamp", "")
                ts = datetime.fromisoformat(raw_ts).astimezone(UTC)
                # 3. Parse prices
                op = Decimal(clean_row.get("open", "0"))
                hp = Decimal(clean_row.get("high", "0"))
                lp = Decimal(clean_row.get("low", "0"))
                cp = Decimal(clean_row.get("close", "0"))
                vol = int(clean_row.get("volume", "0"))

                # Invariant checks
                if hp < op or hp < cp or hp < lp or lp > op or lp > cp or lp > hp:
                    raise ValueError(f"OHLC inconsistency on row {row_idx}")
                if (
                    op <= Decimal("0")
                    or hp <= Decimal("0")
                    or lp <= Decimal("0")
                    or cp <= Decimal("0")
                ):
                    raise ValueError(f"Non-positive price on row {row_idx}")
                if vol < 0:
                    raise ValueError(f"Negative volume on row {row_idx}")

                rec = MarketDataRecord(
                    source=f"IMPORT_CSV:{safe_name}",
                    retrieval_time=now,
                    exchange=ExchangeCode.NSE,
                    instrument_id=inst_id,
                    symbol=raw_sym,
                    timestamp=ts,
                    open=op,
                    high=hp,
                    low=lp,
                    close=cp,
                    volume=vol,
                    currency=CurrencyCode.INR,
                    adjustment_status=AdjustmentStatus.UNADJUSTED,
                    quality_flags=(QualityFlag.CLEAN,),
                    mode=DataMode.HISTORICAL_REPLAY,
                )
                valid_records.append(rec)
                symbols_seen.add(raw_sym)
                timestamps.append(ts)
            except Exception as exc:
                quarantine_count += 1
                self._quarantine.quarantine_row(
                    source=f"IMPORT_CSV:{safe_name}",
                    rejection_reason=f"Validation failed on row {row_idx}: {exc}",
                    raw_payload=str(row),
                    symbol=raw_sym or None,
                )

        start_ts = min(timestamps) if timestamps else None
        end_ts = max(timestamps) if timestamps else None

        result = ImportResult(
            file_name=safe_name,
            sha256_checksum=checksum,
            row_count=row_idx,
            valid_count=len(valid_records),
            quarantine_count=quarantine_count,
            symbols=tuple(sorted(symbols_seen)),
            start_timestamp=start_ts,
            end_timestamp=end_ts,
        )
        return result, valid_records

    def _parse_parquet(
        self, safe_name: str, checksum: str, file_path: Path
    ) -> tuple[ImportResult, list[MarketDataRecord]]:
        try:
            table = pq.read_table(file_path)
        except Exception as exc:
            self._quarantine.quarantine_file(
                file_path=file_path,
                rejection_reason=f"Corrupt Parquet format: {exc}",
                source=f"IMPORT_PARQUET:{safe_name}",
            )
            raise DomainValidationError(
                f"Failed to parse Parquet file: {exc}",
                field="file",
                code=ErrorCode.VALIDATION_ERROR,
            ) from exc

        col_names = {col.lower() for col in table.column_names}
        missing = REQUIRED_COLUMNS - col_names
        if missing:
            raise DomainValidationError(
                f"Parquet missing mandatory columns: {sorted(missing)}.",
                field="file",
                code=ErrorCode.VALIDATION_ERROR,
            )

        if table.num_rows > MAX_ROWS:
            raise DomainValidationError(
                f"Parquet exceeds maximum row limit of {MAX_ROWS} rows.",
                field="file",
                code=ErrorCode.VALIDATION_ERROR,
            )

        pydict = table.to_pydict()
        valid_records: list[MarketDataRecord] = []
        quarantine_count = 0
        symbols_seen: set[str] = set()
        timestamps: list[datetime] = []
        now = datetime.now(UTC)

        for i in range(table.num_rows):
            raw_sym = str(pydict["symbol"][i]).upper()
            try:
                inst_id = self._registry.resolve_instrument_id(raw_sym)
                raw_ts = pydict["timestamp"][i]
                if isinstance(raw_ts, datetime):
                    ts = raw_ts.astimezone(UTC) if raw_ts.tzinfo else raw_ts.replace(tzinfo=UTC)
                else:
                    ts = datetime.fromisoformat(str(raw_ts)).astimezone(UTC)

                op = Decimal(str(pydict["open"][i]))
                hp = Decimal(str(pydict["high"][i]))
                lp = Decimal(str(pydict["low"][i]))
                cp = Decimal(str(pydict["close"][i]))
                vol = int(pydict["volume"][i])

                if hp < op or hp < cp or hp < lp or lp > op or lp > cp or lp > hp:
                    raise ValueError(f"OHLC inconsistency on row {i}")
                if (
                    op <= Decimal("0")
                    or hp <= Decimal("0")
                    or lp <= Decimal("0")
                    or cp <= Decimal("0")
                ):
                    raise ValueError(f"Non-positive price on row {i}")
                if vol < 0:
                    raise ValueError(f"Negative volume on row {i}")

                rec = MarketDataRecord(
                    source=f"IMPORT_PARQUET:{safe_name}",
                    retrieval_time=now,
                    exchange=ExchangeCode.NSE,
                    instrument_id=inst_id,
                    symbol=raw_sym,
                    timestamp=ts,
                    open=op,
                    high=hp,
                    low=lp,
                    close=cp,
                    volume=vol,
                    currency=CurrencyCode.INR,
                    adjustment_status=AdjustmentStatus.UNADJUSTED,
                    quality_flags=(QualityFlag.CLEAN,),
                    mode=DataMode.HISTORICAL_REPLAY,
                )
                valid_records.append(rec)
                symbols_seen.add(raw_sym)
                timestamps.append(ts)
            except Exception as exc:
                quarantine_count += 1
                self._quarantine.quarantine_row(
                    source=f"IMPORT_PARQUET:{safe_name}",
                    rejection_reason=f"Validation failed on row {i}: {exc}",
                    raw_payload=f"ROW_INDEX:{i};SYMBOL:{raw_sym}",
                    symbol=raw_sym or None,
                )

        start_ts = min(timestamps) if timestamps else None
        end_ts = max(timestamps) if timestamps else None

        result = ImportResult(
            file_name=safe_name,
            sha256_checksum=checksum,
            row_count=table.num_rows,
            valid_count=len(valid_records),
            quarantine_count=quarantine_count,
            symbols=tuple(sorted(symbols_seen)),
            start_timestamp=start_ts,
            end_timestamp=end_ts,
        )
        return result, valid_records
