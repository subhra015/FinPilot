"""CSRF protection and Sliding Window Rate Limiting tests (SEC-09, SEC-15, SEC-16, Layer 12).

Governed by:
- OWASP CSRF Prevention Cheat Sheet
- SECURITY_CHECKLIST.md SEC-09, SEC-15, SEC-16
- Layer 12 Gate: CSRF protection, Origin validation, sliding window rate limiting.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from finpilot.auth.csrf import (
    generate_csrf_token,
    verify_csrf_token,
    verify_origin_and_referer,
)
from finpilot.auth.rate_limiter import (
    RateLimitExceededError,
    SlidingWindowRateLimiter,
)


def test_csrf_token_generation_and_verification():
    """CSRF token generated for a session verifies only for that exact session."""
    session_id = "sess_abc123xyz789"
    secret = "test-csrf-secret-key-at-least-32-chars-long"

    token = generate_csrf_token(session_id, secret_key=secret)
    assert len(token) == 64  # SHA-256 HMAC hex

    # Same session and secret verifies
    assert verify_csrf_token(token, session_id, secret_key=secret) is True

    # Different session fails
    assert verify_csrf_token(token, "sess_different_session", secret_key=secret) is False

    # Tampered token fails
    assert verify_csrf_token(token[:-4] + "0000", session_id, secret_key=secret) is False

    # Empty token fails
    assert verify_csrf_token("", session_id, secret_key=secret) is False


def test_csrf_origin_validation():
    """Origin validation enforces strict match against CORS allowlist."""
    allowlist = ["http://localhost:3000", "http://127.0.0.1:3000"]

    req_valid = MagicMock()
    req_valid.headers = {"origin": "http://localhost:3000"}
    assert verify_origin_and_referer(req_valid, allowed_origins=allowlist) is True

    # Unknown cross-origin fails
    req_invalid = MagicMock()
    req_invalid.headers = {"origin": "https://evil-attacker.example.com"}
    assert verify_origin_and_referer(req_invalid, allowed_origins=allowlist) is False

    # Valid referer fallback if origin absent
    req_referer = MagicMock()
    req_referer.headers = {"referer": "http://127.0.0.1:3000/dashboard"}
    assert verify_origin_and_referer(req_referer, allowed_origins=allowlist) is True

    # Invalid referer fallback fails
    req_bad_ref = MagicMock()
    req_bad_ref.headers = {"referer": "https://evil-attacker.example.com/steal"}
    assert verify_origin_and_referer(req_bad_ref, allowed_origins=allowlist) is False


def test_rate_limiter_allows_under_limit():
    """Requests under limit succeed and report accurate remaining count."""
    limiter = SlidingWindowRateLimiter()
    key = "user_test_allow"

    allowed, remaining, retry_after = limiter.is_allowed(key, max_requests=5, window_seconds=60)
    assert allowed is True
    assert remaining == 4
    assert retry_after == 0


def test_rate_limiter_enforces_limit_and_blocks():
    """Exceeding max_requests raises RateLimitExceededError with retry_after."""
    limiter = SlidingWindowRateLimiter()
    key = "ip_test_block"
    max_requests = 3
    window_seconds = 10

    for _ in range(max_requests):
        limiter.enforce("login", key, max_requests=max_requests, window_seconds=window_seconds)

    # 4th request must be rejected
    with pytest.raises(RateLimitExceededError) as exc_info:
        limiter.enforce("login", key, max_requests=max_requests, window_seconds=window_seconds)

    err = exc_info.value
    assert err.retry_after > 0
    assert err.max_requests == max_requests
    assert err.window_seconds == window_seconds


def test_rate_limiter_sliding_window_recovery():
    """Rate limit resets as timestamps slide out of the window."""
    limiter = SlidingWindowRateLimiter()
    key = "short_window"
    max_requests = 2
    window_seconds = 1

    limiter.enforce("action", key, max_requests=max_requests, window_seconds=window_seconds)
    limiter.enforce("action", key, max_requests=max_requests, window_seconds=window_seconds)

    # Immediately blocked
    with pytest.raises(RateLimitExceededError):
        limiter.enforce("action", key, max_requests=max_requests, window_seconds=window_seconds)

    # Sleep slightly past window
    time.sleep(1.05)

    # Now allowed again
    allowed, remaining, _ = limiter.is_allowed(
        f"action:{key}", max_requests=max_requests, window_seconds=window_seconds
    )
    assert allowed is True
    assert remaining == 1
