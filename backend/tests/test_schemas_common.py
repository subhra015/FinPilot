"""Common schema, pagination, timestamp, sorting, and error sanitization tests (Layer 3)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from finpilot.schemas import (
    DateRangeFilter,
    DomainValidationError,
    ErrorCode,
    ErrorResponse,
    PaginationParams,
    SortDirection,
    SortOrderSpec,
    normalize_to_utc,
    sanitize_error_message,
)


def test_pagination_bounds_and_defaults() -> None:
    p = PaginationParams()
    assert p.page == 1
    assert p.page_size == 50
    assert p.offset == 0
    assert p.limit == 50

    custom = PaginationParams(page=3, page_size=25)
    assert custom.offset == 50
    assert custom.limit == 25

    # Page < 1 rejected
    with pytest.raises(ValidationError):
        PaginationParams(page=0)

    # Page size > 100 rejected
    with pytest.raises(ValidationError):
        PaginationParams(page_size=101)

    # Page size < 1 rejected
    with pytest.raises(ValidationError):
        PaginationParams(page_size=0)


def test_date_range_filter_bounds() -> None:
    d1 = date(2026, 1, 1)
    d2 = date(2026, 6, 1)
    dr = DateRangeFilter(start_date=d1, end_date=d2)
    assert dr.start_date == d1
    assert dr.end_date == d2

    # Inverted date range rejected
    with pytest.raises((DomainValidationError, ValidationError)) as exc_inv:
        DateRangeFilter(start_date=d2, end_date=d1)
    assert "start_date" in str(exc_inv.value).lower()

    # Oversized date span (> 366 days) rejected
    with pytest.raises((DomainValidationError, ValidationError)) as exc_span:
        DateRangeFilter(start_date=date(2024, 1, 1), end_date=date(2026, 1, 1))
    assert "exceeds maximum allowed" in str(exc_span.value).lower()


def test_timestamp_utc_normalization_and_naive_rejection() -> None:
    # 1. Timezone-aware IST timestamp normalized to UTC
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    dt_ist = datetime(2026, 10, 31, 9, 15, 0, tzinfo=ist_tz)
    utc = normalize_to_utc(dt_ist)
    assert utc.tzinfo == UTC
    assert utc.hour == 3
    assert utc.minute == 45

    # 2. ISO string with timezone
    iso_str = "2026-10-31T09:15:00+05:30"
    utc_from_str = normalize_to_utc(iso_str)
    assert utc_from_str == utc

    # 3. Naive timestamp rejected (no timezone offset)
    naive_dt = datetime(2026, 10, 31, 9, 15, 0)
    with pytest.raises(DomainValidationError) as exc_naive:
        normalize_to_utc(naive_dt)
    assert "without timezone" in str(exc_naive.value).lower()

    # 4. Unparseable string rejected
    with pytest.raises(DomainValidationError) as exc_unparse:
        normalize_to_utc("invalid-timestamp-format")
    assert "unparseable" in str(exc_unparse.value).lower()


def test_dynamic_sort_allowlist_and_injection_rejection() -> None:
    # Valid allowed field
    allowed = {"id", "symbol", "created_at"}
    spec = SortOrderSpec(field="symbol", direction=SortDirection.DESC)
    assert spec.validate_allowed(allowed) == "symbol"

    # Disallowed field rejected
    disallowed_spec = SortOrderSpec(field="password_hash")
    with pytest.raises(DomainValidationError) as exc_disallow:
        disallowed_spec.validate_allowed(allowed)
    assert "not an allowed sorting field" in str(exc_disallow.value)

    # SQL injection payload rejected by syntax validation
    with pytest.raises((DomainValidationError, ValidationError)):
        SortOrderSpec(field="symbol; DROP TABLE instruments; --")

    with pytest.raises((DomainValidationError, ValidationError)):
        SortOrderSpec(field="symbol UNION SELECT * FROM users")


def test_error_message_sanitization_removes_paths_sql_and_secrets() -> None:
    # Path sanitization
    raw_path_err = "File not found at D:\\Projects\\FinPilot\\backend\\secret.key on Windows"
    clean_path = sanitize_error_message(raw_path_err)
    assert "D:\\Projects" not in clean_path
    assert "[PATH_REDACTED]" in clean_path

    # SQL query sanitization
    raw_sql_err = "Database error: SELECT password_hash FROM users WHERE id = 1 failed"
    clean_sql = sanitize_error_message(raw_sql_err)
    assert "SELECT" not in clean_sql
    assert "[DATABASE_QUERY_REDACTED]" in clean_sql

    # Credential sanitization
    raw_cred_err = (
        "Failed to connect to postgresql+psycopg://app:SECRET_PASS_999@db.internal:5432/db"
    )
    clean_cred = sanitize_error_message(raw_cred_err)
    assert "SECRET_PASS_999" not in clean_cred
    assert "[REDACTED]@" in clean_cred

    # ErrorResponse structure
    resp = ErrorResponse.from_message(raw_path_err, code=ErrorCode.RESOURCE_NOT_FOUND)
    assert resp.code == ErrorCode.RESOURCE_NOT_FOUND
    assert "[PATH_REDACTED]" in resp.error
