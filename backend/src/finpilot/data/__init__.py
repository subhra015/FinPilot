"""Data layer: adapters, audit, quarantine, and import subsystem (Layer 4)."""

from __future__ import annotations

from .adapters import (
    BaseDataProviderAdapter,
    CsvFileAdapter,
    NseBhavcopyAdapter,
    ParquetFileAdapter,
    SyntheticDataProviderAdapter,
)
from .audit import MarketDataAuditor
from .enums import AdjustmentStatus, AuditVerdict, DataAnomalyType, QualityFlag
from .importer import SafeDataImporter
from .models import (
    DataAnomaly,
    DataAuditReport,
    ImportResult,
    MarketDataRecord,
    QuarantinedRecord,
)
from .quarantine import QuarantineManager

__all__ = [
    "AdjustmentStatus",
    "AuditVerdict",
    "BaseDataProviderAdapter",
    "CsvFileAdapter",
    "DataAnomaly",
    "DataAnomalyType",
    "DataAuditReport",
    "ImportResult",
    "MarketDataAuditor",
    "MarketDataRecord",
    "NseBhavcopyAdapter",
    "ParquetFileAdapter",
    "QualityFlag",
    "QuarantineManager",
    "QuarantinedRecord",
    "SafeDataImporter",
    "SyntheticDataProviderAdapter",
]
