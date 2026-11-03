"""Cross-Site Request Forgery (CSRF) and Origin validation middleware/helpers (SEC-16, Layer 12).

Governed by:
- OWASP Cross-Site Request Forgery Prevention Cheat Sheet
- SECURITY_CHECKLIST.md SEC-16
- Layer 12 Gate: Double submit / session-bound CSRF token and origin check for mutating routes.
"""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlparse

from fastapi import Request

from finpilot.schemas.errors import PermissionDeniedError

CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def generate_csrf_token(session_id_hash: str, secret_key: str) -> str:
    """Generate a deterministic HMAC-SHA256 CSRF token cryptographically bound to the session."""
    key = secret_key.encode("utf-8")
    msg = f"csrf:{session_id_hash}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def verify_csrf_token(
    submitted_token: str | None,
    session_id_hash: str,
    secret_key: str,
) -> bool:
    """Verify submitted CSRF token matches the session-bound expected token."""
    if not submitted_token:
        return False
    expected = generate_csrf_token(session_id_hash, secret_key)
    return hmac.compare_digest(submitted_token.strip(), expected)


def verify_origin_and_referer(
    request: Request,
    allowed_origins: list[str],
) -> bool:
    """Verify Origin or Referer header matches allowed CORS origins.

    Protects against cross-origin forged requests.
    """
    origin = request.headers.get("Origin") or request.headers.get("origin")
    referer = request.headers.get("Referer") or request.headers.get("referer")

    # If neither Origin nor Referer is provided, reject if cross-site or state-changing
    if not origin and not referer:
        # In strict browsers, state-changing requests include Origin or Sec-Fetch-Site
        sec_fetch_site = request.headers.get("Sec-Fetch-Site")
        return not (sec_fetch_site and sec_fetch_site in ("cross-site",))

    target_origin = origin
    if not target_origin and referer:
        parsed = urlparse(referer)
        target_origin = f"{parsed.scheme}://{parsed.netloc}"

    if target_origin:
        clean_target = target_origin.rstrip("/")
        normalized_allowed = [o.rstrip("/") for o in allowed_origins if o]
        return clean_target in normalized_allowed

    return True


def enforce_csrf(
    request: Request,
    session_id_hash: str,
    secret_key: str,
    allowed_origins: list[str],
) -> None:
    """Validate CSRF protection for cookie-authenticated mutating requests.

    Raises PermissionDeniedError on mismatch or forged origin.
    """
    if request.method in SAFE_HTTP_METHODS:
        return

    # 1. Validate Origin / Referer
    if allowed_origins and not verify_origin_and_referer(request, allowed_origins):
        raise PermissionDeniedError("CSRF verification failed: untrusted origin.")

    # 2. Validate CSRF token header
    submitted_token = request.headers.get(CSRF_HEADER_NAME)
    if not verify_csrf_token(submitted_token, session_id_hash, secret_key):
        raise PermissionDeniedError("CSRF verification failed: invalid or missing anti-CSRF token.")
