"""Instrument schema, identity bounds, and known-symbol registry tests (Layer 3)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from finpilot.db.enums import CurrencyCode, ExchangeCode, InstrumentStatus, MarketType
from finpilot.schemas import (
    DomainValidationError,
    ErrorCode,
    InstrumentCreate,
    KnownInstrumentRegistry,
)


def test_valid_instrument_creation() -> None:
    inst = InstrumentCreate(
        isin="INE002A01018",
        symbol="RELIANCE",
        name="Reliance Industries Limited",
        market=MarketType.EQUITY,
        exchange=ExchangeCode.NSE,
        currency=CurrencyCode.INR,
        lot_size=1,
        tick_size=Decimal("0.0500"),
        status=InstrumentStatus.ACTIVE,
    )
    assert inst.isin == "INE002A01018"
    assert inst.symbol == "RELIANCE"
    assert inst.exchange == ExchangeCode.NSE
    assert inst.currency == CurrencyCode.INR


@pytest.mark.parametrize(
    "invalid_isin",
    [
        "INE002A0101",  # 11 chars
        "INE002A010189",  # 13 chars
        "123002A01018",  # Starts with numbers instead of 2-letter country code
        "ine002a01018",  # Lowercase
        "INE002A0101!",  # Special character
        "",  # Empty
    ],
)
def test_invalid_isin_rejected(invalid_isin: str) -> None:
    with pytest.raises((DomainValidationError, ValidationError)) as exc:
        InstrumentCreate(
            isin=invalid_isin,
            symbol="TEST",
            name="Test",
        )
    assert "isin" in str(exc.value).lower()


@pytest.mark.parametrize(
    "invalid_symbol",
    [
        "",  # Empty
        "   ",  # Whitespace
        "RELIANCE INDUSTRIES",  # Space
        "RELIANCE; DROP TABLE",  # SQL Injection
        "RELIANCE/EQ",  # Slash
        "A" * 21,  # Exceeds max length 20
    ],
)
def test_invalid_symbol_rejected(invalid_symbol: str) -> None:
    with pytest.raises((DomainValidationError, ValidationError)) as exc:
        InstrumentCreate(
            isin="INE002A01018",
            symbol=invalid_symbol,
            name="Test",
        )
    assert "symbol" in str(exc.value).lower()


def test_known_instrument_registry_resolves_and_rejects_arbitrary_identity() -> None:
    registry = KnownInstrumentRegistry({"RELIANCE": 101, "TCS": 102, "INFY": 103})

    # Known symbols resolve correctly (case-insensitive)
    assert registry.resolve_instrument_id("RELIANCE") == 101
    assert registry.resolve_instrument_id("reliance") == 101
    assert registry.resolve_instrument_id("TCS") == 102

    # Arbitrary client-supplied symbols rejected
    with pytest.raises(DomainValidationError) as exc:
        registry.resolve_instrument_id("UNKNOWN_CO_ARBITRARY")
    assert "unknown or unauthorized instrument symbol" in str(exc.value).lower()
    assert exc.value.code == ErrorCode.INVALID_INSTRUMENT


def test_non_positive_lot_and_tick_size_rejected() -> None:
    with pytest.raises(ValidationError):
        InstrumentCreate(
            isin="INE002A01018",
            symbol="RELIANCE",
            name="Reliance",
            lot_size=0,
        )

    with pytest.raises(ValidationError):
        InstrumentCreate(
            isin="INE002A01018",
            symbol="RELIANCE",
            name="Reliance",
            tick_size=Decimal("0.0000"),
        )
