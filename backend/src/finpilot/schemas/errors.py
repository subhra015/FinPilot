"""Safe error models and message sanitization (SEC-06, SEC-07, Layer 3).

Guarantees that error messages returned to clients or logged never leak:
- Internal filesystem paths (e.g. Windows drives, Unix paths).
- Raw SQL queries or database syntax error details.
- Secrets, tokens, or credentials.
"""

from __future__ import annotations

import enum
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_PATH_PATTERN = re.compile(
    r"([A-Za-z]:\\[^:\s\n\"']+|/(?:[a-zA-Z0-9._-]+/)+[a-zA-Z0-9._-]+)"
)
_SQL_PATTERN = re.compile(
    r"""(?ix)
    \b(select\s+.+?\s+from|insert\s+into|update\s+.+?\s+set|delete\s+from|
       drop\s+table|alter\s+table|union\s+select|syntax\s+error\s+at\s+or\s+near)\b
    """
)
_CREDENTIAL_PATTERN = re.compile(r"(://[^:\s/@]+):([^@\s/]+)@")
_TOKEN_PATTERN = re.compile(
    r"(?i)\b(bearer\s+[A-Za-z0-9\-._~+/]+=*|token\s*=\s*['\"]?[^'\"]+)"
)


def sanitize_error_message(message: str) -> str:
    """Sanitize error message to prevent leaking internal paths, SQL, or secrets."""
    if not isinstance(message, str):
        return "An internal error occurred."

    sanitized = message
    # 1. Sanitize credentials and tokens
    sanitized = _CREDENTIAL_PATTERN.sub(r"\1:[REDACTED]@", sanitized)
    sanitized = _TOKEN_PATTERN.sub("[REDACTED_TOKEN]", sanitized)

    # 2. Sanitize SQL fragments
    sanitized = _SQL_PATTERN.sub("[DATABASE_QUERY_REDACTED]", sanitized)

    # 3. Sanitize filesystem paths
    sanitized = _PATH_PATTERN.sub("[PATH_REDACTED]", sanitized)

    return sanitized


class ErrorCode(enum.StrEnum):
    """Standardized API error codes."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INSTRUMENT = "INVALID_INSTRUMENT"
    INVALID_CANDLE = "INVALID_CANDLE"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorDetail(BaseModel):
    """Specific field-level error detail."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str | None = Field(default=None, max_length=100)
    message: str = Field(..., max_length=500)
    code: str = Field(default=ErrorCode.VALIDATION_ERROR.value, max_length=50)


class ErrorResponse(BaseModel):
    """Standard safe API error response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    error: str = Field(..., max_length=500, description="Safe high-level error summary")
    code: ErrorCode = Field(default=ErrorCode.VALIDATION_ERROR)
    details: list[ErrorDetail] = Field(default_factory=list, max_length=100)

    @classmethod
    def from_message(
        cls,
        message: str,
        code: ErrorCode = ErrorCode.VALIDATION_ERROR,
        details: list[ErrorDetail] | None = None,
    ) -> ErrorResponse:
        """Construct sanitized error response."""
        safe_msg = sanitize_error_message(message)
        return cls(error=safe_msg, code=code, details=details or [])


class DomainValidationError(ValueError):
    """Raised when domain constraints or validation rules are violated."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        code: ErrorCode = ErrorCode.VALIDATION_ERROR,
    ) -> None:
        self.raw_message = message
        self.field = field
        self.code = code
        super().__init__(sanitize_error_message(message))


class InvalidStateTransitionError(DomainValidationError):
    """Raised when an illegal lifecycle state transition is attempted."""

    def __init__(
        self, current_state: Any, target_state: Any, entity: str = "Order"
    ) -> None:
        msg = f"Invalid {entity} state transition from '{current_state}' to '{target_state}'."
        super().__init__(msg, field="status", code=ErrorCode.INVALID_STATE_TRANSITION)


class PermissionDeniedError(Exception):
    """Raised when a user attempts to access a resource they do not own."""

    def __init__(
        self, message: str = "Access denied: unauthorized resource scope."
    ) -> None:
        super().__init__(sanitize_error_message(message))
        self.code = ErrorCode.PERMISSION_DENIED


class ResourceNotFoundError(Exception):
    """Raised when a requested resource does not exist in the user's scope."""

    def __init__(self, message: str = "Resource not found.") -> None:
        super().__init__(sanitize_error_message(message))
        self.code = ErrorCode.RESOURCE_NOT_FOUND
