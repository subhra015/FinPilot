"""Unit tests for SecurityAuditLogger and secret redaction (SEC-02, SEC-08, Layer 14)."""

from __future__ import annotations

import pytest

from finpilot.workflow.audit_logger import (
    SecurityAuditLogger,
    SuspiciousActivityType,
    audit_logger,
    redact_sensitive_data,
)


@pytest.fixture(autouse=True)
def clean_audit_logger() -> None:
    audit_logger.clear()


def test_secret_redaction_in_dictionaries() -> None:
    sensitive_dict = {
        "username": "trader@finpilot.test",
        "password": "SuperSecretPassphrase123!",
        "session_id": "sess_abcdef1234567890",
        "api_key": "sk_live_1234567890abcdef",
        "totp_code": "123456",
        "metadata": {
            "token": "secret_token_val",
            "nested": {"private_key": "-----BEGIN PRIVATE KEY-----"},
        },
    }

    cleaned = redact_sensitive_data(sensitive_dict)

    assert cleaned["username"] == "trader@finpilot.test"
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["session_id"] == "[REDACTED]"
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["totp_code"] == "[REDACTED]"
    assert cleaned["metadata"]["token"] == "[REDACTED]"
    assert cleaned["metadata"]["nested"]["private_key"] == "[REDACTED]"


def test_secret_redaction_in_strings() -> None:
    bearer_str = "Authorization header: Bearer ya29.a0AfH6SMBxyz123456789"
    cleaned = redact_sensitive_data(bearer_str)
    assert "[REDACTED_TOKEN]" in cleaned
    assert "ya29" not in cleaned

    cookie_str = "Cookie: theme=dark; finpilot_session=abc123xyz456; other=1"
    cleaned_cookie = redact_sensitive_data(cookie_str)
    assert "finpilot_session=[REDACTED]" in cleaned_cookie
    assert "abc123xyz456" not in cleaned_cookie


def test_audit_logger_records_all_suspicious_activity_types() -> None:
    # 1. Auth failure
    rec1 = audit_logger.log_auth_failure(
        actor="anonymous_ip",
        endpoint="/api/auth/login",
        reason="Bad credentials",
        context={"password": "attempted_plaintext_password"},
    )
    assert rec1.activity_type == SuspiciousActivityType.AUTHENTICATION_FAILURE
    assert rec1.details["password"] == "[REDACTED]"

    # 2. Authz denial
    rec2 = audit_logger.log_authz_denial(
        actor="user_123",
        endpoint="/api/portfolios/999",
        resource_id="Portfolio:999",
        reason="IDOR detected",
    )
    assert rec2.activity_type == SuspiciousActivityType.AUTHORIZATION_DENIAL

    # 3. Rate limit
    rec3 = audit_logger.log_rate_limit(actor="ip_456", endpoint="/api/auth/login", limit=5, window_seconds=60)
    assert rec3.activity_type == SuspiciousActivityType.RATE_LIMIT_TRIGGER

    # 4. Invalid import
    rec4 = audit_logger.log_invalid_import(actor="admin_1", filename="bad.csv", reason="Corrupt header", byte_size=500)
    assert rec4.activity_type == SuspiciousActivityType.INVALID_IMPORT

    # 5. Provider failure
    rec5 = audit_logger.log_provider_failure(provider_name="NSE_FEED", endpoint="/ticks", error_message="Socket timeout")
    assert rec5.activity_type == SuspiciousActivityType.PROVIDER_FAILURE

    # 6. Risk setting change
    rec6 = audit_logger.log_risk_change(actor="admin_sec", changes={"max_daily_loss": 800}, is_kill_switch=True)
    assert rec6.activity_type == SuspiciousActivityType.RISK_SETTING_CHANGE
    assert rec6.severity == "CRITICAL"

    # Verify retrieval
    all_records = audit_logger.get_records()
    assert len(all_records) == 6
    auth_records = audit_logger.get_records(SuspiciousActivityType.AUTHENTICATION_FAILURE)
    assert len(auth_records) == 1
