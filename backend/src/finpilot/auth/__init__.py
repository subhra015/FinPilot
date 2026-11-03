"""Authentication and session management package (Layer 12).

Exports Argon2id password hashing, NIST SP 800-63B-4 policy validation,
RFC 6238 TOTP MFA, opaque server-side session management, CSRF validation,
and sliding window rate limiting.
"""

from __future__ import annotations

from .csrf import CSRF_HEADER_NAME, enforce_csrf, generate_csrf_token, verify_csrf_token
from .mfa import generate_totp_code, generate_totp_secret, get_totp_uri, verify_totp_code
from .passwords import (
    COMMON_PASSWORDS_BLOCKLIST,
    hash_password,
    validate_password_policy,
    verify_password,
)
from .rate_limiter import RateLimitExceededError, SlidingWindowRateLimiter, limiter
from .service import AuthService
from .sessions import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    SessionManager,
)

__all__ = [
    "hash_password",
    "verify_password",
    "validate_password_policy",
    "COMMON_PASSWORDS_BLOCKLIST",
    "generate_totp_secret",
    "generate_totp_code",
    "verify_totp_code",
    "get_totp_uri",
    "SessionManager",
    "SESSION_COOKIE_NAME",
    "CSRF_COOKIE_NAME",
    "generate_csrf_token",
    "verify_csrf_token",
    "enforce_csrf",
    "CSRF_HEADER_NAME",
    "limiter",
    "SlidingWindowRateLimiter",
    "RateLimitExceededError",
    "AuthService",
]
