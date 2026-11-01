"""Market data provider adapter tests (Layer 4)."""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from finpilot.data import (
    AdjustmentStatus,
    CsvFileAdapter,
    NseBhavcopyAdapter,
    ParquetFileAdapter,
    QualityFlag,
    SyntheticDataProviderAdapter,
)
from finpilot.db.enums import CurrencyCode, DataMode, ExchangeCode
from finpilot.schemas.errors import DomainValidationError


def test_synthetic_adapter_session_generation() -> None:
    adapter = SyntheticDataProviderAdapter()
    trading_day = date(2026, 10, 30)  # Friday

    bars = adapter.fetch_bars("RELIANCE", trading_day)
    # Exactly 75 5-minute bars in a complete normal NSE trading session
    assert len(bars) == 75

    first_bar = bars[0]
    assert first_bar.symbol == "RELIANCE"
    assert first_bar.exchange == ExchangeCode.NSE
    assert first_bar.currency == CurrencyCode.INR
    assert first_bar.mode == DataMode.SYNTHETIC_DEMO
    assert first_bar.adjustment_status == AdjustmentStatus.UNADJUSTED
    assert QualityFlag.CLEAN in first_bar.quality_flags

    # Invariants on prices
    for b in bars:
        assert b.high >= b.open
        assert b.high >= b.close
        assert b.high >= b.low
        assert b.low <= b.open
        assert b.low <= b.close
        assert b.volume >= 0
        assert b.open > Decimal("0")

    # Weekend generates no bars
    weekend_day = date(2026, 10, 31)  # Saturday
    assert len(adapter.fetch_bars("RELIANCE", weekend_day)) == 0

    # Provenance metadata
    meta = adapter.get_provider_metadata()
    assert meta.provider_name == "FinPilot Synthetic Generator"
    assert meta.terms_verified is True


def test_bhavcopy_adapter_parsing_and_filtering() -> None:
    adapter = NseBhavcopyAdapter()
    csv_sample = (
        "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN\n"
        "RELIANCE,EQ,2500.00,2520.00,2495.00,2510.00,2510.00,2490.00,1500000,3750000000,30-OCT-2026,45000,INE002A01018\n"
        "RELIANCE,BE,2480.00,2490.00,2470.00,2475.00,2475.00,2470.00,10000,24750000,30-OCT-2026,500,INE002A01018\n"
        "TCS,EQ,3800.00,3850.00,3790.00,3830.00,3830.00,3795.00,800000,3050000000,30-OCT-2026,30000,INE467B01029\n"
    )
    loaded = adapter.load_bhavcopy_csv(csv_sample)
    # BE series is filtered out; only EQ series loaded (RELIANCE and TCS)
    assert loaded == 2

    target_date = date(2026, 10, 30)
    reliance_bars = adapter.fetch_bars("RELIANCE", target_date)
    assert len(reliance_bars) == 1
    rec = reliance_bars[0]
    assert rec.symbol == "RELIANCE"
    assert rec.instrument_id == 101
    assert rec.open == Decimal("2500.0000")
    assert rec.high == Decimal("2520.0000")
    assert rec.close == Decimal("2510.0000")
    assert rec.volume == 1500000
    assert rec.exchange == ExchangeCode.NSE
    assert rec.mode == DataMode.HISTORICAL_REPLAY


def test_parquet_and_csv_file_adapters(tmp_path: Path) -> None:
    # 1. Create a sample Parquet file
    parquet_file = tmp_path / "test_5m.parquet"
    data = {
        "symbol": ["RELIANCE", "RELIANCE"],
        "timestamp": ["2026-10-30T03:45:00+00:00", "2026-10-30T03:50:00+00:00"],
        "open": ["2500.0", "2505.0"],
        "high": ["2510.0", "2515.0"],
        "low": ["2495.0", "2500.0"],
        "close": ["2505.0", "2510.0"],
        "volume": [1000, 2000],
    }
    table = pa.Table.from_pydict(data)
    pq.write_table(table, parquet_file)

    checksum = hashlib.sha256(parquet_file.read_bytes()).hexdigest()
    adapter = ParquetFileAdapter(parquet_file, expected_sha256=checksum)
    bars = adapter.fetch_bars("RELIANCE", date(2026, 10, 30))
    assert len(bars) == 2

    # Checksum mismatch test
    with pytest.raises(DomainValidationError) as exc:
        ParquetFileAdapter(parquet_file, expected_sha256="0" * 64)
    assert "checksum mismatch" in str(exc.value).lower()

    # 2. Create a sample CSV file
    csv_file = tmp_path / "test_5m.csv"
    csv_content = """symbol,timestamp,open,high,low,close,volume
RELIANCE,2026-10-30T03:45:00+00:00,2500.0,2510.0,2495.0,2505.0,1000
RELIANCE,2026-10-30T03:50:00+00:00,2505.0,2515.0,2500.0,2510.0,2000
"""
    csv_file.write_text(csv_content, encoding="utf-8")
    csv_checksum = hashlib.sha256(csv_file.read_bytes()).hexdigest()
    csv_adapter = CsvFileAdapter(csv_file, expected_sha256=csv_checksum)
    csv_bars = csv_adapter.fetch_bars("RELIANCE", date(2026, 10, 30))
    assert len(csv_bars) == 2
