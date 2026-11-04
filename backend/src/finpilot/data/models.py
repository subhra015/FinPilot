"""Data models for market records, anomalies, audit reports, and quarantine (Layer 4)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from finpilot.db.enums import CurrencyCode, DataMode, ExchangeCode
from finpilot.schemas.common import normalize_to_utc

from .enums import AdjustmentStatus, AuditVerdict, DataAnomalyType, QualityFlag


class MarketDataRecord(BaseModel):
    """Canonical validated market data record with full provenance and quality metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(..., min_length=1, max_length=100, description="Provider source identity")
    retrieval_time: datetime = Field(..., description="Timestamp when record was retrieved (UTC)")
    exchange: ExchangeCode = Field(default=ExchangeCode.NSE)
    instrument_id: int = Field(..., ge=1, description="Stable instrument identifier")
    symbol: str = Field(..., min_length=1, max_length=20, description="NSE Trading symbol")
    timestamp: datetime = Field(..., description="5-minute bar timestamp (UTC)")
    open: Decimal = Field(..., gt=Decimal("0"), le=Decimal("10000000.0000"))
    high: Decimal = Field(..., gt=Decimal("0"), le=Decimal("10000000.0000"))
    low: Decimal = Field(..., gt=Decimal("0"), le=Decimal("10000000.0000"))
    close: Decimal = Field(..., gt=Decimal("0"), le=Decimal("10000000.0000"))
    volume: int = Field(..., ge=0, description="Traded volume (>= 0)")
    currency: CurrencyCode = Field(default=CurrencyCode.INR)
    adjustment_status: AdjustmentStatus = Field(default=AdjustmentStatus.UNADJUSTED)
    quality_flags: tuple[QualityFlag, ...] = Field(default_factory=lambda: (QualityFlag.CLEAN,))
    mode: DataMode = Field(default=DataMode.HISTORICAL_REPLAY)

    @field_validator("retrieval_time", "timestamp", mode="before")
    @classmethod
    def normalize_record_timestamps(cls, v: Any) -> datetime:
        return normalize_to_utc(v)


class QuarantinedRecord(BaseModel):
    """Record representing a rejected market data row or file preserved for audit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: str = Field(..., min_length=1, max_length=100)
    quarantined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    rejection_reason: str = Field(..., min_length=1, max_length=500)
    raw_payload: str = Field(..., description="Raw string or serialized input")
    symbol: str | None = Field(default=None, max_length=20)
    timestamp: datetime | None = Field(default=None)


class DataAnomaly(BaseModel):
    """An individual data quality anomaly detected during audit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    anomaly_type: DataAnomalyType
    severity: str = Field(..., pattern="^(INFO|WARNING|ERROR|CRITICAL)$")
    description: str = Field(..., min_length=1, max_length=500)
    timestamp: datetime | None = None
    observed_value: str | None = None
    expected_value: str | None = None


class DataAuditReport(BaseModel):
    """Per-symbol/day audit report documenting data quality, anomalies, and coverage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(..., min_length=1, max_length=20)
    audit_date: date
    session_expected_bars: int = Field(default=75, description="Expected 5m bars for full session")
    total_bars: int = Field(..., ge=0)
    valid_bars: int = Field(..., ge=0)
    quarantined_bars: int = Field(..., ge=0)
    missing_bars: int = Field(..., ge=0)
    completion_pct: float = Field(..., ge=0.0, le=100.0)
    quality_score: float = Field(..., ge=0.0, le=1.0)
    anomalies: tuple[DataAnomaly, ...] = Field(default_factory=tuple)
    verdict: AuditVerdict = Field(default=AuditVerdict.PASS)
    provenance_source: str = Field(..., min_length=1, max_length=100)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ImportResult(BaseModel):
    """Summary of a completed file import operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    file_name: str = Field(..., min_length=1, max_length=255)
    sha256_checksum: str = Field(..., min_length=64, max_length=64)
    row_count: int = Field(..., ge=0)
    valid_count: int = Field(..., ge=0)
    quarantine_count: int = Field(..., ge=0)
    symbols: tuple[str, ...] = Field(default_factory=tuple)
    start_timestamp: datetime | None = None
    end_timestamp: datetime | None = None
    quarantine_path: str | None = None
