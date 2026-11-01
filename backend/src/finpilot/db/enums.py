"""Domain enumerations for the persistence layer (Layer 2).

Aligned with ARCHITECTURE.md §4-5 and DATA_AND_PERFORMANCE_POLICY.md §3.
"""

from __future__ import annotations

import enum


class MarketType(enum.StrEnum):
    """Supported market segments in V1."""

    EQUITY = "EQUITY"


class ExchangeCode(enum.StrEnum):
    """Supported exchanges (V1 is strictly NSE cash)."""

    NSE = "NSE"


class CurrencyCode(enum.StrEnum):
    """Operating currency."""

    INR = "INR"


class InstrumentStatus(enum.StrEnum):
    """Trading status of an instrument."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELISTED = "DELISTED"


class DataMode(enum.StrEnum):
    """Execution and research modes (DATA_AND_PERFORMANCE_POLICY.md §3).

    Cross-mode mixing in any evidence output is strictly prohibited.
    """

    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    FORWARD_PAPER = "FORWARD_PAPER"
    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"


class OrderType(enum.StrEnum):
    """Supported order types."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderSide(enum.StrEnum):
    """Order sides (long-only: BUY to open, SELL to close)."""

    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(enum.StrEnum):
    """Lifecycle status of a simulated order."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class LedgerEventType(enum.StrEnum):
    """Event types recorded in the append-only prediction/event ledger."""

    DECISION = "DECISION"
    ORDER_CREATED = "ORDER_CREATED"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    FILL = "FILL"
    PARTIAL_FILL = "PARTIAL_FILL"
    EXIT = "EXIT"
    EXPIRY = "EXPIRY"
    FEE_APPLIED = "FEE_APPLIED"
    BALANCE_UPDATE = "BALANCE_UPDATE"
