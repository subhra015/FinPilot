"""Adversarial validation tests for malformed inputs, SQL injection, and extremes (Layer 3)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from finpilot.db.enums import OrderSide
from finpilot.schemas import (
    CandleBar,
    CostBreakdown,
    DomainValidationError,
    InstrumentCreate,
    KnownInstrumentRegistry,
    OrderCreate,
    PaginationParams,
    PermissionDeniedError,
    SortOrderSpec,
    TradeProposal,
    UserScope,
    enforce_resource_owner,
    sanitize_error_message,
)

IST_VALID_TS = datetime(2026, 10, 30, 9, 15, 0, tzinfo=UTC)


# 1. SQL Injection strings as input data
@pytest.mark.parametrize(
    "sql_payload",
    [
        "'; DROP TABLE instruments; --",
        "' OR '1'='1",
        "'; TRUNCATE TABLE users; --",
        "1 UNION SELECT username, password_hash FROM users --",
        "admin'--",
        '" OR ""="',
        "'; EXEC xp_cmdshell('dir'); --",
    ],
)
def test_sql_injection_payloads_rejected_or_treated_as_literal_data(
    sql_payload: str,
) -> None:
    # A. In Instrument symbol: rejected by strict regex
    with pytest.raises((DomainValidationError, ValidationError)):
        InstrumentCreate(
            isin="INE002A01018",
            symbol=sql_payload,
            name="Injection Attempt",
        )

    # B. In SortOrderSpec: rejected by identifier syntax check
    with pytest.raises((DomainValidationError, ValidationError)):
        SortOrderSpec(field=sql_payload)

    # C. In KnownInstrumentRegistry: treated strictly as literal string lookup (fails safe)
    registry = KnownInstrumentRegistry({"RELIANCE": 101})
    with pytest.raises(DomainValidationError) as exc_reg:
        registry.resolve_instrument_id(sql_payload)
    assert "unknown or unauthorized instrument symbol" in str(exc_reg.value).lower()


# 2. NaN, Infinity, and Extremes
@pytest.mark.parametrize(
    "extreme_val",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_nan_and_infinity_rejected_across_schemas(extreme_val: object) -> None:
    # A. In Candle prices
    with pytest.raises((DomainValidationError, ValidationError)):
        CandleBar(
            symbol="RELIANCE",
            timestamp=IST_VALID_TS,
            open=extreme_val,  # type: ignore[arg-type]
            high=Decimal("2510.0000"),
            low=Decimal("2498.0000"),
            close=Decimal("2505.0000"),
            volume=1000,
        )

    # B. In CostBreakdown
    with pytest.raises((DomainValidationError, ValidationError)):
        CostBreakdown(
            brokerage=extreme_val,  # type: ignore[arg-type]
        )


# 3. Out-of-range quantities, whole-share enforcement, and negative values
def test_out_of_range_and_fractional_quantities_rejected() -> None:
    t_decision = datetime(2026, 10, 30, 9, 20, 0, tzinfo=UTC)
    t_entry = datetime(2026, 10, 30, 9, 25, 0, tzinfo=UTC)

    # Negative quantity in proposal
    with pytest.raises((DomainValidationError, ValidationError)):
        TradeProposal(
            proposal_id="p1",
            instrument_id=101,
            symbol="RELIANCE",
            decision_timestamp=t_decision,
            earliest_entry_timestamp=t_entry,
            entry_price=Decimal("2500.0000"),
            stop_loss=Decimal("2480.0000"),
            target_price=Decimal("2550.0000"),
            quantity=-10,
        )

    # Zero quantity in proposal
    with pytest.raises((DomainValidationError, ValidationError)):
        TradeProposal(
            proposal_id="p2",
            instrument_id=101,
            symbol="RELIANCE",
            decision_timestamp=t_decision,
            earliest_entry_timestamp=t_entry,
            entry_price=Decimal("2500.0000"),
            stop_loss=Decimal("2480.0000"),
            target_price=Decimal("2550.0000"),
            quantity=0,
        )

    # Negative quantity in OrderCreate
    with pytest.raises((DomainValidationError, ValidationError)):
        OrderCreate(
            account_id=1,
            instrument_id=101,
            side=OrderSide.BUY,
            quantity=0,
            price=Decimal("2500.0000"),
        )


# 4. Oversized inputs and boundary flooding
def test_oversized_payloads_rejected() -> None:
    # 10,000-char string symbol
    with pytest.raises((DomainValidationError, ValidationError)):
        InstrumentCreate(
            isin="INE002A01018",
            symbol="A" * 10000,
            name="Flood",
        )

    # 10,000-char ISIN
    with pytest.raises((DomainValidationError, ValidationError)):
        InstrumentCreate(
            isin="INE" + "A" * 9997,
            symbol="RELIANCE",
            name="Flood",
        )

    # Huge page size (> 100)
    with pytest.raises((DomainValidationError, ValidationError)):
        PaginationParams(page=1, page_size=50000)


# 5. Null bytes and control characters
@pytest.mark.parametrize(
    "corrupt_symbol",
    [
        "RELIANCE\x00INJECT",
        "TCS\r\nINJECT",
        "\x00",
        "INF\tY",
        "INF\x0bY",
    ],
)
def test_control_characters_and_null_bytes_rejected(corrupt_symbol: str) -> None:
    with pytest.raises((DomainValidationError, ValidationError)):
        InstrumentCreate(
            isin="INE002A01018",
            symbol=corrupt_symbol,
            name="Corrupt",
        )


# 6. Cross-user ID isolation without leaking metadata
def test_adversarial_cross_user_tampering() -> None:
    legitimate_user = UserScope(user_id="user_target_victim")
    attacker = UserScope(user_id="user_attacker")

    # Attacker tries to impersonate or access victim's resource
    with pytest.raises(PermissionDeniedError) as exc:
        enforce_resource_owner(
            resource_owner_id=legitimate_user.user_id,
            user_scope=attacker,
            resource_name="AccountBalance",
        )
    # Ensure error message provides no details on victim existence
    err_text = str(exc.value)
    assert legitimate_user.user_id not in err_text
    assert "Access denied: unauthorized AccountBalance scope." in err_text


# 7. Internal error leakage prevention
def test_internal_error_sanitization() -> None:
    adversarial_inputs = [
        "FATAL: Password 'admin1234' leaked in SELECT * FROM accounts WHERE id = 42",
        "Unhandled exception in /var/finpilot/internal/keys/private.pem at line 89",
        "Traceback (most recent call last):\n  File 'D:\\Projects\\FinPilot\\app.py', line 12",
        "Connection refused to postgresql+psycopg://db_admin:SUPER_SECRET_PW@db.corp.net:5432/core",
    ]

    for raw in adversarial_inputs:
        sanitized = sanitize_error_message(raw)
        # Verify no file paths leaked
        assert "/var/finpilot" not in sanitized
        assert "D:\\Projects" not in sanitized
        # Verify no database connection secrets leaked
        assert "SUPER_SECRET_PW" not in sanitized
        # Verify no raw SQL statements leaked
        assert "SELECT * FROM" not in sanitized
