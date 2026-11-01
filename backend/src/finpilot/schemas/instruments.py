"""Instrument schemas and strict identity validation contracts (Layer 3).

Enforces:
- Strict symbol, exchange, market, and currency formats.
- Stable ISIN (12 chars).
- Rejection of client-supplied arbitrary instrument identity via known instrument validation.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from finpilot.db.enums import CurrencyCode, ExchangeCode, InstrumentStatus, MarketType

from .errors import DomainValidationError, ErrorCode

SYMBOL_REGEX = re.compile(r"^[A-Z0-9&-]{1,20}$")
ISIN_REGEX = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


class InstrumentBase(BaseModel):
    """Base instrument properties."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    isin: str = Field(
        ..., min_length=12, max_length=12, description="Permanent 12-character ISIN"
    )
    symbol: str = Field(
        ..., min_length=1, max_length=20, description="Active NSE trading symbol"
    )
    name: str = Field(
        ..., min_length=1, max_length=100, description="Instrument legal / display name"
    )
    market: MarketType = Field(default=MarketType.EQUITY)
    exchange: ExchangeCode = Field(default=ExchangeCode.NSE)
    currency: CurrencyCode = Field(default=CurrencyCode.INR)
    lot_size: int = Field(default=1, ge=1, le=100000)
    tick_size: Decimal = Field(
        default=Decimal("0.0500"), gt=Decimal("0"), le=Decimal("100.0000")
    )
    status: InstrumentStatus = Field(default=InstrumentStatus.ACTIVE)

    @field_validator("isin")
    @classmethod
    def validate_isin_format(cls, v: str) -> str:
        clean = v.strip()
        if not ISIN_REGEX.match(clean):
            raise DomainValidationError(
                f"Invalid ISIN format: {v!r}. Must match 12-char pattern {ISIN_REGEX.pattern}.",
                field="isin",
                code=ErrorCode.INVALID_INSTRUMENT,
            )
        return clean

    @field_validator("symbol")
    @classmethod
    def validate_symbol_format(cls, v: str) -> str:
        clean = v.strip()
        if not SYMBOL_REGEX.match(clean):
            raise DomainValidationError(
                f"Invalid symbol format: {v!r}. Must match pattern {SYMBOL_REGEX.pattern}.",
                field="symbol",
                code=ErrorCode.INVALID_INSTRUMENT,
            )
        return clean


class InstrumentCreate(InstrumentBase):
    """Payload to register/create a new instrument."""


class InstrumentRead(InstrumentBase):
    """Read representation of an instrument."""

    id: int
    created_at: datetime
    updated_at: datetime


class KnownInstrumentRegistry:
    """Registry maintaining verified, known instrument symbols to IDs.

    Guarantees that downstream trading, replay, or risk checks operate strictly on verified
    instrument records rather than client-supplied arbitrary identifiers.
    """

    def __init__(self, known_symbols_to_id: dict[str, int] | None = None) -> None:
        self._registry = {k.upper(): v for k, v in (known_symbols_to_id or {}).items()}

    def register(self, symbol: str, instrument_id: int) -> None:
        self._registry[symbol.upper()] = instrument_id

    def resolve_instrument_id(self, symbol: str) -> int:
        """Resolve a symbol against the known instrument registry.

        Rejects arbitrary client-supplied identity per Layer 3 requirement.
        """
        clean = symbol.strip().upper()
        inst_id = self._registry.get(clean)
        if inst_id is None:
            raise DomainValidationError(
                f"Unknown or unauthorized instrument symbol: {symbol!r}. "
                "Must match a verified instrument record.",
                field="symbol",
                code=ErrorCode.INVALID_INSTRUMENT,
            )
        return inst_id
