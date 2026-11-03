"""Multi-Factor Authentication (MFA) via RFC 6238 TOTP and WebAuthn schemas (Layer 12).

Governed by:
- RFC 6238 (TOTP: Time-Based One-Time Password Algorithm)
- RFC 4226 (HOTP: An HMAC-Based One-Time Password Algorithm)
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-09
- Layer 12 Gate: Phishing-resistant / TOTP MFA mandatory for admins, optional for users.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import UTC, datetime
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field


def generate_totp_secret(num_bytes: int = 20) -> str:
    """Generate a high-entropy Base32-encoded secret for RFC 6238 TOTP (160 bits)."""
    random_bytes = secrets.token_bytes(num_bytes)
    return base64.b32encode(random_bytes).decode("ascii").replace("=", "")


def _get_time_counter(ts: datetime | None = None, time_step: int = 30) -> int:
    """Compute the 30-second epoch counter step."""
    epoch_seconds = int(ts.timestamp()) if ts is not None else int(time.time())
    return epoch_seconds // time_step


def generate_totp_code(secret: str, ts: datetime | None = None, time_step: int = 30) -> str:
    """Generate a standard 6-digit RFC 6238 TOTP code."""
    # Ensure correct padding for Base32 decoding
    padded_secret = secret.upper()
    missing_padding = len(padded_secret) % 8
    if missing_padding:
        padded_secret += "=" * (8 - missing_padding)

    key = base64.b32decode(padded_secret)
    counter = _get_time_counter(ts, time_step)
    counter_bytes = struct.pack(">Q", counter)

    # Compute HMAC-SHA1
    hmac_digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()

    # Dynamic truncation (RFC 4226 §5.3)
    offset = hmac_digest[-1] & 0x0F
    code_int = struct.unpack(">I", hmac_digest[offset : offset + 4])[0] & 0x7FFFFFFF
    token = code_int % 1000000

    return f"{token:06d}"


def verify_totp_code(
    secret: str,
    submitted_code: str,
    ts: datetime | None = None,
    time_step: int = 30,
    window: int = 1,
) -> bool:
    """Verify a TOTP code against secret with drift tolerance window (+- 1 time step)."""
    if not submitted_code or len(submitted_code.strip()) != 6:
        return False

    submitted_clean = submitted_code.strip()
    current_counter = _get_time_counter(ts, time_step)

    # Check intervals [counter - window, ..., counter + window]
    for step_offset in range(-window, window + 1):
        test_ts = datetime.fromtimestamp((current_counter + step_offset) * time_step, tz=UTC)
        expected_code = generate_totp_code(secret, ts=test_ts, time_step=time_step)
        if hmac.compare_digest(submitted_clean, expected_code):
            return True

    return False


def get_totp_uri(secret: str, email: str, issuer: str = "FinPilot AI") -> str:
    """Generate a standard otpauth:// URI for QR code enrollment."""
    safe_issuer = quote(issuer)
    safe_email = quote(email)
    return (
        f"otpauth://totp/{safe_issuer}:{safe_email}"
        f"?secret={secret}&issuer={safe_issuer}&algorithm=SHA1&digits=6&period=30"
    )


# ---------------------------------------------------------------------------
# WebAuthn / Passkey Contract Schemas (Layer 12 specification)
# ---------------------------------------------------------------------------


class WebAuthnRegistrationChallenge(BaseModel):
    """Server challenge issued for registering a phishing-resistant passkey."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    challenge: str = Field(..., min_length=32)
    rp_id: str = Field(default="localhost")
    rp_name: str = Field(default="FinPilot AI")
    user_id: str
    user_email: str
    timeout_ms: int = Field(default=60000)
    attestation: str = Field(default="none")


class WebAuthnAssertionChallenge(BaseModel):
    """Server challenge issued for authenticating via a registered passkey."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    challenge: str = Field(..., min_length=32)
    rp_id: str = Field(default="localhost")
    timeout_ms: int = Field(default=60000)
    user_verification: str = Field(default="preferred")
