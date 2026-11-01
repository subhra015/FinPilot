"""Database foundation and persistence models (Layer 2).

Governed by ARCHITECTURE.md §5 and ACCEPTANCE_GATES.md §Layer 2.
"""

from __future__ import annotations

from .base import Base, create_engine_from_settings, create_session_factory
from .enums import (
    CurrencyCode,
    DataMode,
    ExchangeCode,
    InstrumentStatus,
    LedgerEventType,
    MarketType,
    OrderSide,
    OrderStatus,
    OrderType,
)
from .models import (
    Account,
    DatasetManifest,
    Instrument,
    InstrumentSymbolHistory,
    LedgerEvent,
    Order,
    Portfolio,
    Position,
)
from .roles import ADMIN_ROLE, APP_ROLE, generate_role_setup_script

__all__ = [
    "Base",
    "create_engine_from_settings",
    "create_session_factory",
    "MarketType",
    "ExchangeCode",
    "CurrencyCode",
    "InstrumentStatus",
    "DataMode",
    "OrderType",
    "OrderSide",
    "OrderStatus",
    "LedgerEventType",
    "Instrument",
    "InstrumentSymbolHistory",
    "DatasetManifest",
    "Account",
    "Portfolio",
    "Position",
    "Order",
    "LedgerEvent",
    "ADMIN_ROLE",
    "APP_ROLE",
    "generate_role_setup_script",
]
