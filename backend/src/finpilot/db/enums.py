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


class UserRole(enum.StrEnum):
    """User authorization roles (SEC-01, SEC-09, Layer 12)."""

    USER = "USER"
    ADMIN = "ADMIN"
    SERVICE = "SERVICE"


class MFAMethod(enum.StrEnum):
    """Multi-Factor Authentication methods."""

    TOTP = "TOTP"
    WEBAUTHN = "WEBAUTHN"


class LedgerEventType(enum.StrEnum):
    """Event types recorded in the append-only prediction/event ledger."""

    ACCEPTED = "ACCEPTED"
    DECISION = "DECISION"
    NO_TRADE = "NO_TRADE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    ORDER_CREATED = "ORDER_CREATED"
    FILL = "FILL"
    PARTIAL_FILL = "PARTIAL_FILL"
    ENTRY_UNFILLED = "ENTRY_UNFILLED"
    EXECUTION_UNRESOLVED = "EXECUTION_UNRESOLVED"
    EXIT = "EXIT"
    EXPIRY = "EXPIRY"
    FEE_APPLIED = "FEE_APPLIED"
    BALANCE_UPDATE = "BALANCE_UPDATE"
    CORRECTION = "CORRECTION"
    OPPORTUNITY_OMITTED = "OPPORTUNITY_OMITTED"
    PORTFOLIO_OUTCOME = "PORTFOLIO_OUTCOME"
    HYPOTHETICAL_OUTCOME = "HYPOTHETICAL_OUTCOME"
