"""Data layer enums for market data, quality flags, and audit verdicts (Layer 4)."""

from __future__ import annotations

import enum


class AdjustmentStatus(enum.StrEnum):
    """Corporate action adjustment status for market data."""

    UNADJUSTED = "UNADJUSTED"
    SPLIT_ADJUSTED = "SPLIT_ADJUSTED"
    DIVIDEND_ADJUSTED = "DIVIDEND_ADJUSTED"
    FULLY_ADJUSTED = "FULLY_ADJUSTED"


class QualityFlag(enum.StrEnum):
    """Quality and anomaly flags attached to market data records."""

    CLEAN = "CLEAN"
    ZERO_VOLUME = "ZERO_VOLUME"
    VOLUME_SPIKE = "VOLUME_SPIKE"
    PRICE_JUMP = "PRICE_JUMP"
    SESSION_GAP = "SESSION_GAP"
    UNALIGNED_TIMESTAMP = "UNALIGNED_TIMESTAMP"
    CORPORATE_ACTION_SUSPECT = "CORPORATE_ACTION_SUSPECT"
    CROSS_SOURCE_DISCREPANCY = "CROSS_SOURCE_DISCREPANCY"
    CORRUPTED = "CORRUPTED"


class AuditVerdict(enum.StrEnum):
    """Overall verdict of a per-symbol/day market data audit."""

    PASS = "PASS"
    WARNING = "WARNING"
    REJECTED = "REJECTED"


class DataAnomalyType(enum.StrEnum):
    """Specific categories of anomalies discovered by the auditor."""

    SESSION_MISALIGNMENT = "SESSION_MISALIGNMENT"
    DUPLICATE_BAR = "DUPLICATE_BAR"
    OUT_OF_ORDER_BAR = "OUT_OF_ORDER_BAR"
    MISSING_INTERVAL = "MISSING_INTERVAL"
    INCOMPLETE_SESSION = "INCOMPLETE_SESSION"
    OHLC_INCONSISTENCY = "OHLC_INCONSISTENCY"
    NON_FINITE_PRICE = "NON_FINITE_PRICE"
    NON_POSITIVE_PRICE = "NON_POSITIVE_PRICE"
    NEGATIVE_VOLUME = "NEGATIVE_VOLUME"
    ZERO_VOLUME_EXTENDED = "ZERO_VOLUME_EXTENDED"
    VOLUME_SPIKE = "VOLUME_SPIKE"
    SUSPICIOUS_PRICE_JUMP = "SUSPICIOUS_PRICE_JUMP"
    CORPORATE_ACTION_GAP = "CORPORATE_ACTION_GAP"
    SYMBOL_INVALID_DATE = "SYMBOL_INVALID_DATE"
    CROSS_SOURCE_DISCREPANCY = "CROSS_SOURCE_DISCREPANCY"
