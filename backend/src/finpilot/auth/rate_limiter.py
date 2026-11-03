"""Thread-safe in-memory sliding window rate limiter (SEC-12, Layer 12).

Governed by:
- OWASP Rate Limiting Cheat Sheet
- SECURITY_CHECKLIST.md SEC-12
- Layer 12 Gate: Rate limit login, reset, registration, data import, and expensive endpoints.
"""

from __future__ import annotations

import collections
import threading
import time

from finpilot.schemas.errors import PermissionDeniedError


class RateLimitExceededError(PermissionDeniedError):
    """Raised when request rate exceeds allowed threshold."""

    def __init__(
        self,
        message: str,
        retry_after: int,
        max_requests: int | None = None,
        window_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.max_requests = max_requests
        self.window_seconds = window_seconds


class SlidingWindowRateLimiter:
    """Thread-safe sliding window rate limiter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Key: (category, identifier) -> list of unix timestamps
        self._buckets: collections.defaultdict[tuple[str, str], list[float]] = (
            collections.defaultdict(list)
        )

    def check_rate_limit(
        self,
        category: str,
        identifier: str,
        max_requests: int,
        window_seconds: int,
        current_time: float | None = None,
    ) -> tuple[bool, int]:
        """Check if request is permitted.

        Returns tuple of (is_allowed, retry_after_seconds).
        """
        now = current_time if current_time is not None else time.time()
        cutoff = now - window_seconds
        bucket_key = (category, identifier)

        with self._lock:
            timestamps = self._buckets[bucket_key]
            # Prune old timestamps
            valid_timestamps = [t for t in timestamps if t > cutoff]
            self._buckets[bucket_key] = valid_timestamps

            if len(valid_timestamps) >= max_requests:
                earliest_active = valid_timestamps[0]
                retry_after = max(1, int(earliest_active + window_seconds - now))
                return False, retry_after

            # Allow and append
            valid_timestamps.append(now)
            return True, 0

    def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        """Convenience method returning (is_allowed, remaining_requests, retry_after)."""
        allowed, retry_after = self.check_rate_limit(
            category="default",
            identifier=key,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
        remaining = 0
        if allowed:
            with self._lock:
                used = len(self._buckets[("default", key)])
                remaining = max(0, max_requests - used)
        return allowed, remaining, retry_after

    def enforce(
        self,
        category: str,
        identifier: str,
        max_requests: int,
        window_seconds: int,
        current_time: float | None = None,
    ) -> None:
        """Enforce rate limit, raising RateLimitExceededError if breached."""
        allowed, retry_after = self.check_rate_limit(
            category=category,
            identifier=identifier,
            max_requests=max_requests,
            window_seconds=window_seconds,
            current_time=current_time,
        )
        if not allowed:
            raise RateLimitExceededError(
                f"Rate limit exceeded for {category}. Please retry after {retry_after} seconds.",
                retry_after=retry_after,
                max_requests=max_requests,
                window_seconds=window_seconds,
            )

    def reset(self) -> None:
        """Clear all rate limit buckets (useful for tests)."""
        with self._lock:
            self._buckets.clear()


# Global in-memory rate limiter instance
limiter = SlidingWindowRateLimiter()

# Standard Rate Configurations:
# - Login: 5 requests / 60 seconds
# - Registration: 3 requests / 60 seconds
# - Password Reset: 3 requests / 60 seconds
# - Data Import: 10 requests / 60 seconds
# - ML Inference / Queries: 30 requests / 60 seconds
LOGIN_RATE_LIMIT = (5, 60)
REGISTER_RATE_LIMIT = (3, 60)
RESET_RATE_LIMIT = (3, 60)
IMPORT_RATE_LIMIT = (10, 60)
INFERENCE_RATE_LIMIT = (30, 60)
