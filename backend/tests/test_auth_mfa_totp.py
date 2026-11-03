"""RFC 6238 TOTP Multi-Factor Authentication tests (SEC-01, Layer 12).

Governed by:
- RFC 6238 (TOTP: Time-Based One-Time Password Algorithm)
- SECURITY_CHECKLIST.md SEC-01
- Layer 12 Gate: Phishing-resistant passkeys contract and standard RFC 6238 TOTP.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from finpilot.auth.mfa import (
    generate_totp_code,
    generate_totp_secret,
    get_totp_uri,
    verify_totp_code,
)


def test_totp_secret_generation():
    """Secret must be valid 32-character RFC 4648 Base32 string."""
    secret = generate_totp_secret()
    assert len(secret) == 32
    # Base32 characters only: A-Z, 2-7
    assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in secret)


def test_totp_code_generation_format():
    """Generated code must be a 6-digit numeric string."""
    secret = generate_totp_secret()
    code = generate_totp_code(secret)
    assert len(code) == 6
    assert code.isdigit()


def test_totp_verification_current_time():
    """Current TOTP code verifies successfully."""
    secret = generate_totp_secret()
    code = generate_totp_code(secret)
    assert verify_totp_code(secret, code) is True


def test_totp_time_drift_tolerance():
    """TOTP verification allows ±1 time step window (30 seconds before/after)."""
    secret = generate_totp_secret()
    now = datetime.now(UTC)

    # 1 step in the past (-30 seconds)
    past_code = generate_totp_code(secret, ts=now - timedelta(seconds=28))
    assert verify_totp_code(secret, past_code, ts=now) is True

    # 1 step in the future (+30 seconds)
    future_code = generate_totp_code(secret, ts=now + timedelta(seconds=28))
    assert verify_totp_code(secret, future_code, ts=now) is True

    # 3 steps in the past (-90 seconds) must fail
    way_past_code = generate_totp_code(secret, ts=now - timedelta(seconds=95))
    assert verify_totp_code(secret, way_past_code, ts=now) is False

    # 3 steps in the future (+90 seconds) must fail
    way_future_code = generate_totp_code(secret, ts=now + timedelta(seconds=95))
    assert verify_totp_code(secret, way_future_code, ts=now) is False


def test_totp_invalid_codes():
    """Invalid, short, or malformed codes must be safely rejected."""
    secret = generate_totp_secret()
    assert verify_totp_code(secret, "000000") is False
    assert verify_totp_code(secret, "12345") is False
    assert verify_totp_code(secret, "abcdef") is False
    assert verify_totp_code(secret, "") is False


def test_totp_uri_generation():
    """URI generation for authenticator apps contains required issuer and account params."""
    secret = "JBSWY3DPEHPK3PXP"
    uri = get_totp_uri(secret, email="admin@finpilot.test", issuer="FinPilot")
    assert uri.startswith("otpauth://totp/FinPilot:admin%40finpilot.test?")
    assert "secret=JBSWY3DPEHPK3PXP" in uri
    assert "issuer=FinPilot" in uri
    assert "algorithm=SHA1" in uri
    assert "digits=6" in uri
    assert "period=30" in uri
