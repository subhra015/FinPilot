"""Security and operational audit logger for suspicious activity (SEC-08, Layer 14).

Monitors, logs, and alerts on:
- Authentication failures (brute force, bad credentials, nonexistent user)
- Authorization denials (IDOR, role mismatch, non-admin interventions)
- Rate-limit triggers (sliding window abuse)
- Invalid or malformed imports
- Provider failures and feed interruptions
- Changes to risk settings and emergency interventions

Strict Invariant (SEC-02, SEC-08):
All secrets, session tokens, passwords, and authorization headers are automatically
redacted before persistence or emission.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("finpilot.security_audit")

_REDACTION_PATTERNS = [
    (re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"password['\"]?\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE), "password='[REDACTED]'"),
    (re.compile(r"session_id['\"]?\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE), "session_id='[REDACTED]'"),
    (re.compile(r"finpilot_session=([^;\s]+)", re.IGNORECASE), "finpilot_session=[REDACTED]"),
    (re.compile(r"totp_code['\"]?\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE), "totp_code='[REDACTED]'"),
]

_SENSITIVE_KEYS = {
    "password",
    "passphrase",
    "secret",
    "api_key",
    "token",
    "access_token",
    "session_id",
    "cookie",
    "authorization",
    "totp_code",
    "private_key",
}


def redact_sensitive_data(val: Any) -> Any:
    """Recursively redact passwords, tokens, and secret parameters from structures and strings."""
    if isinstance(val, dict):
        cleaned: dict[str, Any] = {}
        for k, v in val.items():
            if any(s in k.lower() for s in _SENSITIVE_KEYS):
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = redact_sensitive_data(v)
        return cleaned
    elif isinstance(val, list):
        return [redact_sensitive_data(item) for item in val]
    elif isinstance(val, str):
        result = val
        for pattern, replacement in _REDACTION_PATTERNS:
            result = pattern.sub(replacement, result)
        return result
    return val


class SuspiciousActivityType(str, Enum):
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    AUTHORIZATION_DENIAL = "AUTHORIZATION_DENIAL"
    RATE_LIMIT_TRIGGER = "RATE_LIMIT_TRIGGER"
    INVALID_IMPORT = "INVALID_IMPORT"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    RISK_SETTING_CHANGE = "RISK_SETTING_CHANGE"


class SuspiciousActivityRecord(BaseModel):
    event_id: str = Field(default_factory=lambda: f"AUD-{uuid.uuid4().hex[:12]}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    activity_type: SuspiciousActivityType
    actor: str
    endpoint_or_component: str
    details: dict[str, Any]
    severity: str = "WARNING"  # INFO, WARNING, CRITICAL


class SecurityAuditLogger:
    """Thread-safe security audit log sink with automatic redaction."""

    _instance: SecurityAuditLogger | None = None

    def __new__(cls) -> SecurityAuditLogger:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._events = []
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_events"):
            self._events: list[SuspiciousActivityRecord] = []

    def record_activity(
        self,
        activity_type: SuspiciousActivityType,
        actor: str,
        endpoint_or_component: str,
        details: dict[str, Any],
        severity: str = "WARNING",
    ) -> SuspiciousActivityRecord:
        """Record a suspicious security event with full secret redaction."""
        cleaned_details = redact_sensitive_data(details)
        record = SuspiciousActivityRecord(
            activity_type=activity_type,
            actor=actor,
            endpoint_or_component=endpoint_or_component,
            details=cleaned_details,
            severity=severity,
        )
        self._events.append(record)
        log_msg = (
            f"SECURITY_AUDIT: type={record.activity_type.value} "
            f"actor={record.actor} component={record.endpoint_or_component} "
            f"severity={record.severity} details={record.details}"
        )
        if severity == "CRITICAL":
            logger.critical(log_msg)
        else:
            logger.warning(log_msg)
        return record

    def log_auth_failure(
        self,
        actor: str,
        endpoint: str,
        reason: str,
        context: dict[str, Any] | None = None,
    ) -> SuspiciousActivityRecord:
        details = {"reason": reason, **(context or {})}
        return self.record_activity(
            SuspiciousActivityType.AUTHENTICATION_FAILURE,
            actor=actor,
            endpoint_or_component=endpoint,
            details=details,
            severity="WARNING",
        )

    def log_authz_denial(
        self,
        actor: str,
        endpoint: str,
        resource_id: str,
        reason: str,
    ) -> SuspiciousActivityRecord:
        details = {"resource_id": resource_id, "reason": reason}
        return self.record_activity(
            SuspiciousActivityType.AUTHORIZATION_DENIAL,
            actor=actor,
            endpoint_or_component=endpoint,
            details=details,
            severity="WARNING",
        )

    def log_rate_limit(
        self,
        actor: str,
        endpoint: str,
        limit: int,
        window_seconds: int,
    ) -> SuspiciousActivityRecord:
        details = {"limit": limit, "window_seconds": window_seconds}
        return self.record_activity(
            SuspiciousActivityType.RATE_LIMIT_TRIGGER,
            actor=actor,
            endpoint_or_component=endpoint,
            details=details,
            severity="WARNING",
        )

    def log_invalid_import(
        self,
        actor: str,
        filename: str,
        reason: str,
        byte_size: int | None = None,
    ) -> SuspiciousActivityRecord:
        details = {"filename": filename, "reason": reason, "byte_size": byte_size}
        return self.record_activity(
            SuspiciousActivityType.INVALID_IMPORT,
            actor=actor,
            endpoint_or_component="data_importer",
            details=details,
            severity="WARNING",
        )

    def log_provider_failure(
        self,
        provider_name: str,
        endpoint: str,
        error_message: str,
        is_stale: bool = False,
    ) -> SuspiciousActivityRecord:
        details = {
            "provider": provider_name,
            "error": error_message,
            "is_stale": is_stale,
        }
        return self.record_activity(
            SuspiciousActivityType.PROVIDER_FAILURE,
            actor="market_data_ingestion",
            endpoint_or_component=endpoint,
            details=details,
            severity="CRITICAL" if is_stale else "WARNING",
        )

    def log_risk_change(
        self,
        actor: str,
        changes: dict[str, Any],
        is_kill_switch: bool = False,
    ) -> SuspiciousActivityRecord:
        details = {"changes": changes, "is_kill_switch": is_kill_switch}
        severity = "CRITICAL" if is_kill_switch else "WARNING"
        return self.record_activity(
            SuspiciousActivityType.RISK_SETTING_CHANGE,
            actor=actor,
            endpoint_or_component="risk_engine",
            details=details,
            severity=severity,
        )

    def get_records(
        self,
        activity_type: SuspiciousActivityType | None = None,
        limit: int = 100,
    ) -> list[SuspiciousActivityRecord]:
        """Retrieve recent security audit records filtered by type."""
        records = [
            r for r in self._events if activity_type is None or r.activity_type == activity_type
        ]
        return records[-limit:]

    def clear(self) -> None:
        """Clear recorded events (for isolated unit tests)."""
        self._events.clear()


audit_logger = SecurityAuditLogger()
