"""Common schemas, pagination bounds, timestamp normalization, and safe sorting (Layer 3).

Enforces:
- Timezone-aware timestamps with UTC normalization; rejects naive/ambiguous timestamps.
- Explicit pagination and date-range bounds.
- Strict field allowlists for dynamic sorting to prevent SQL injection (SEC-10).
"""

from __future__ import annotations

import enum
import re
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import DomainValidationError, ErrorCode

SQL_INJECTION_CHARS = re.compile(
    r"['\";]|--|/\*|\*/|\b(drop|select|union|insert|delete)\b", re.IGNORECASE
)


class SortDirection(enum.StrEnum):
    """Sort order direction."""

    ASC = "ASC"
    DESC = "DESC"


class PaginationParams(BaseModel):
    """Standardized pagination parameters with strict bounds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    page: int = Field(default=1, ge=1, le=100000, description="Page index (1-based)")
    page_size: int = Field(default=50, ge=1, le=100, description="Page size (1-100)")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class DateRangeFilter(BaseModel):
    """Bounded date-range filter for historical queries."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None)
    max_days_span: int = Field(default=366, ge=1, le=1825, exclude=True)

    @model_validator(mode="after")
    def validate_range(self) -> DateRangeFilter:
        if self.start_date is not None and self.end_date is not None:
            if self.start_date > self.end_date:
                raise DomainValidationError(
                    f"start_date ({self.start_date}) must be less than or equal to "
                    f"end_date ({self.end_date}).",
                    field="start_date",
                    code=ErrorCode.VALIDATION_ERROR,
                )
            span = (self.end_date - self.start_date).days
            if span > self.max_days_span:
                raise DomainValidationError(
                    f"Requested date range span ({span} days) exceeds maximum allowed "
                    f"({self.max_days_span} days).",
                    field="end_date",
                    code=ErrorCode.VALIDATION_ERROR,
                )
        return self


def normalize_to_utc(ts: Any) -> datetime:
    """Validate that timestamp is timezone-aware and normalize to UTC.

    Rejects naive, ambiguous, or unparseable timestamps per Layer 3 contract.
    """
    if ts is None:
        raise DomainValidationError("Timestamp cannot be None.", field="timestamp")

    dt: datetime
    if isinstance(ts, datetime):
        dt = ts
    elif isinstance(ts, str):
        cleaned = ts.strip()
        if not cleaned:
            raise DomainValidationError("Timestamp string cannot be empty.", field="timestamp")
        try:
            dt = datetime.fromisoformat(cleaned)
        except ValueError as exc:
            raise DomainValidationError(
                f"Unparseable ISO timestamp: {cleaned!r}",
                field="timestamp",
            ) from exc
    else:
        raise DomainValidationError(
            f"Invalid timestamp type: {type(ts).__name__}",
            field="timestamp",
        )

    # Reject naive timestamps: timezone awareness is mandatory
    if dt.tzinfo is None:
        raise DomainValidationError(
            f"Ambiguous timestamp without timezone: {dt.isoformat()}. "
            "Explicit timezone offset required.",
            field="timestamp",
        )

    # Normalize to UTC
    return dt.astimezone(UTC)


class SortOrderSpec(BaseModel):
    """Dynamic sorting specification protected by strict field allowlists (SEC-10)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(..., min_length=1, max_length=50)
    direction: SortDirection = Field(default=SortDirection.ASC)

    @field_validator("field")
    @classmethod
    def check_safe_field_syntax(cls, v: str) -> str:
        clean = v.strip()
        if SQL_INJECTION_CHARS.search(clean) or not clean.isidentifier():
            raise DomainValidationError(
                f"Invalid sort field identifier: {v!r}",
                field="field",
            )
        return clean

    def validate_allowed(self, allowed_fields: set[str]) -> str:
        """Verify that the sort field belongs to the explicit allowlist."""
        if self.field not in allowed_fields:
            raise DomainValidationError(
                f"Field '{self.field}' is not an allowed sorting field. "
                f"Allowed: {sorted(allowed_fields)}",
                field="field",
            )
        return self.field
