"""File-based data provider adapters for Parquet and CSV stores (Layer 4)."""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime
from decimal import Decimal
import hashlib
from pathlib import Path
from typing import Sequence

import pyarrow.parquet as pq  # type: ignore[import-untyped]

from finpilot.db.enums import CurrencyCode, DataMode, ExchangeCode
from finpilot.schemas.datasets import DataSourceMetadata
from finpilot.schemas.errors import DomainValidationError
from finpilot.schemas.instruments import KnownInstrumentRegistry

from ..enums import AdjustmentStatus, QualityFlag
from ..models import MarketDataRecord
from .base import BaseDataProviderAdapter


class ParquetFileAdapter(BaseDataProviderAdapter):
    """Adapter reading validated analytical Parquet files with cryptographic checksum verification."""

    def __init__(
        self,
        file_path: Path | str,
        expected_sha256: str | None = None,
        registry: KnownInstrumentRegistry | None = None,
    ) -> None:
        self._path = Path(file_path)
        self._expected_sha256 = expected_sha256.lower() if expected_sha256 else None
        self._registry = registry or KnownInstrumentRegistry({"RELIANCE": 101, "TCS": 102, "INFY": 103})
        self._records: list[MarketDataRecord] = []
        self._load_and_verify()

    @property
    def provider_source(self) -> str:
        return f"PARQUET_FILE:{self._path.name}"

    @property
    def data_mode(self) -> DataMode:
        return DataMode.HISTORICAL_REPLAY

    def get_provider_metadata(self) -> DataSourceMetadata:
        content = self._path.read_bytes() if self._path.exists() else b""
        actual_hash = hashlib.sha256(content).hexdigest()
        now = datetime.now(UTC)
        return DataSourceMetadata(
            source_id=f"PARQUET_STORE_{self._path.stem}",
            provider_name="FinPilot Analytical Parquet Storage",
            terms_verified=True,
            license_reference="FinPilot Internal Analytical Store",
            fetch_timestamp=now,
            provenance_hash=actual_hash,
        )

    def _load_and_verify(self) -> None:
        if not self._path.exists():
            return

        file_bytes = self._path.read_bytes()
        actual_hash = hashlib.sha256(file_bytes).hexdigest()

        if self._expected_sha256 and actual_hash != self._expected_sha256:
            raise DomainValidationError(
                f"Parquet file checksum mismatch. Expected {self._expected_sha256}, got {actual_hash}.",
                field="sha256_checksum",
            )

        table = pq.read_table(self._path)
        pydict = table.to_pydict()
        row_count = table.num_rows
        now = datetime.now(UTC)

        for i in range(row_count):
            sym = str(pydict["symbol"][i]).upper()
            inst_id = self._registry.resolve_instrument_id(sym)
            raw_ts = pydict["timestamp"][i]
            if isinstance(raw_ts, datetime):
                ts = raw_ts.astimezone(UTC) if raw_ts.tzinfo else raw_ts.replace(tzinfo=UTC)
            else:
                ts = datetime.fromisoformat(str(raw_ts)).astimezone(UTC)

            rec = MarketDataRecord(
                source=self.provider_source,
                retrieval_time=now,
                exchange=ExchangeCode.NSE,
                instrument_id=inst_id,
                symbol=sym,
                timestamp=ts,
                open=Decimal(str(pydict["open"][i])),
                high=Decimal(str(pydict["high"][i])),
                low=Decimal(str(pydict["low"][i])),
                close=Decimal(str(pydict["close"][i])),
                volume=int(pydict["volume"][i]),
                currency=CurrencyCode.INR,
                adjustment_status=AdjustmentStatus.UNADJUSTED,
                quality_flags=(QualityFlag.CLEAN,),
                mode=self.data_mode,
            )
            self._records.append(rec)

    def fetch_bars(self, symbol: str, target_date: date) -> Sequence[MarketDataRecord]:
        clean_sym = symbol.strip().upper()
        return [
            r for r in self._records
            if r.symbol == clean_sym and r.timestamp.date() == target_date
        ]


class CsvFileAdapter(BaseDataProviderAdapter):
    """Adapter reading validated CSV files."""

    def __init__(
        self,
        file_path: Path | str,
        expected_sha256: str | None = None,
        registry: KnownInstrumentRegistry | None = None,
    ) -> None:
        self._path = Path(file_path)
        self._expected_sha256 = expected_sha256.lower() if expected_sha256 else None
        self._registry = registry or KnownInstrumentRegistry({"RELIANCE": 101, "TCS": 102, "INFY": 103})
        self._records: list[MarketDataRecord] = []
        self._load_and_verify()

    @property
    def provider_source(self) -> str:
        return f"CSV_FILE:{self._path.name}"

    @property
    def data_mode(self) -> DataMode:
        return DataMode.HISTORICAL_REPLAY

    def get_provider_metadata(self) -> DataSourceMetadata:
        content = self._path.read_bytes() if self._path.exists() else b""
        actual_hash = hashlib.sha256(content).hexdigest()
        now = datetime.now(UTC)
        return DataSourceMetadata(
            source_id=f"CSV_STORE_{self._path.stem}",
            provider_name="FinPilot Analytical CSV Storage",
            terms_verified=True,
            license_reference="FinPilot Internal Analytical Store",
            fetch_timestamp=now,
            provenance_hash=actual_hash,
        )

    def _load_and_verify(self) -> None:
        if not self._path.exists():
            return

        file_bytes = self._path.read_bytes()
        actual_hash = hashlib.sha256(file_bytes).hexdigest()

        if self._expected_sha256 and actual_hash != self._expected_sha256:
            raise DomainValidationError(
                f"CSV file checksum mismatch. Expected {self._expected_sha256}, got {actual_hash}.",
                field="sha256_checksum",
            )

        text = file_bytes.decode("utf-8")
        reader = csv.DictReader(text.splitlines())
        now = datetime.now(UTC)

        for row in reader:
            clean_row = {k.strip().lower(): v.strip() for k, v in row.items() if k}
            sym = clean_row["symbol"].upper()
            inst_id = self._registry.resolve_instrument_id(sym)
            raw_ts = clean_row["timestamp"]
            ts = datetime.fromisoformat(raw_ts).astimezone(UTC)

            rec = MarketDataRecord(
                source=self.provider_source,
                retrieval_time=now,
                exchange=ExchangeCode.NSE,
                instrument_id=inst_id,
                symbol=sym,
                timestamp=ts,
                open=Decimal(clean_row["open"]),
                high=Decimal(clean_row["high"]),
                low=Decimal(clean_row["low"]),
                close=Decimal(clean_row["close"]),
                volume=int(clean_row["volume"]),
                currency=CurrencyCode.INR,
                adjustment_status=AdjustmentStatus.UNADJUSTED,
                quality_flags=(QualityFlag.CLEAN,),
                mode=self.data_mode,
            )
            self._records.append(rec)

    def fetch_bars(self, symbol: str, target_date: date) -> Sequence[MarketDataRecord]:
        clean_sym = symbol.strip().upper()
        return [
            r for r in self._records
            if r.symbol == clean_sym and r.timestamp.date() == target_date
        ]
