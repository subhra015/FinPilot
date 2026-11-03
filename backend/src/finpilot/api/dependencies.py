"""FastAPI dependency injection for authentication, RBAC, DB session, and CSRF (Layer 12).

Governed by:
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-09, SEC-15, SEC-16
- Layer 12 Gate: Server-side authentication, deny-by-default RBAC, object ownership, CSRF.
"""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session as DBSession

from finpilot.auth.csrf import enforce_csrf
from finpilot.auth.sessions import (
    DEFAULT_ABSOLUTE_TIMEOUT_SECONDS,
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    SESSION_COOKIE_NAME,
    SessionManager,
)
from finpilot.config import Settings
from finpilot.db import create_engine_from_settings, create_session_factory
from finpilot.db.enums import UserRole
from finpilot.db.models import User
from finpilot.schemas.errors import AuthenticationRequiredError, PermissionDeniedError

_session_manager = SessionManager(
    idle_timeout_seconds=DEFAULT_IDLE_TIMEOUT_SECONDS,
    absolute_timeout_seconds=DEFAULT_ABSOLUTE_TIMEOUT_SECONDS,
)


def get_db(request: Request) -> Generator[DBSession, None, None]:
    """Provide a transactional SQLAlchemy database session per request."""
    settings: Settings = request.app.state.settings
    if not hasattr(request.app.state, "db_factory"):
        engine = create_engine_from_settings(settings)
        request.app.state.db_factory = create_session_factory(engine)

    session_factory = request.app.state.db_factory
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request,
    db: DBSession = Depends(get_db),
) -> User:
    """Extract and validate the opaque session token from HttpOnly cookie (SEC-01, SEC-15).

    Raises PermissionDeniedError if unauthenticated, expired, or revoked.
    """
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_token:
        raise AuthenticationRequiredError("Authentication required: missing session cookie.")

    validated = _session_manager.validate_session(db=db, raw_token=raw_token)
    if not validated:
        raise AuthenticationRequiredError(
            "Authentication required: invalid, expired, or revoked session."
        )

    user_session, user = validated
    # Store session hash on request state for CSRF checks
    request.state.session_id_hash = user_session.session_id_hash
    request.state.raw_session_token = raw_token
    request.state.current_user = user
    return user


def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Enforce administrative privileges (SEC-09). Deny by default."""
    if current_user.role != UserRole.ADMIN.value:
        raise PermissionDeniedError("Access denied: administrator role required.")
    return current_user


def require_csrf(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> None:
    """Enforce CSRF token and Origin validation for state-changing endpoints (SEC-16)."""
    settings: Settings = request.app.state.settings
    secret_key = (
        settings.secret_key.get_secret_value()
        if settings.secret_key
        else "fallback-dev-secret-key-32chars"
    )
    allowed_origins = list(settings.cors_origins)

    session_id_hash = getattr(request.state, "session_id_hash", None)
    if not session_id_hash:
        raw_token = request.cookies.get(SESSION_COOKIE_NAME, "")
        session_id_hash = SessionManager.hash_session_token(raw_token)

    enforce_csrf(
        request=request,
        session_id_hash=session_id_hash,
        secret_key=secret_key,
        allowed_origins=allowed_origins,
    )


def enforce_resource_ownership(
    resource_owner_user_id: int | str | None,
    current_user: User,
    resource_name: str = "Resource",
) -> None:
    """Prevent Insecure Direct Object References (IDOR).

    User A cannot access User B's resources unless current_user is an administrator.
    """
    if current_user.role == UserRole.ADMIN.value:
        return

    # Check ID match
    is_owner = False
    if (
        isinstance(resource_owner_user_id, int)
        and resource_owner_user_id == current_user.id
        or isinstance(resource_owner_user_id, str)
        and resource_owner_user_id == current_user.user_id
    ):
        is_owner = True

    if not is_owner:
        raise PermissionDeniedError(f"Access denied: unauthorized {resource_name} scope.")
