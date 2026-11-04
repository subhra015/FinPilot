"""Opaque server-side session management and lifecycle control (SEC-15, Layer 12).

Governed by:
- OWASP Session Management Cheat Sheet
- SECURITY_CHECKLIST.md SEC-15
- Layer 12 Gate: Opaque server-side sessions in HttpOnly, Secure, SameSite cookies;
  session rotation, idle (30m) and absolute (12h) timeouts, instant revocation.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session as DBSession

from finpilot.db.models import User, UserSession

# Session lifetime configuration
DEFAULT_IDLE_TIMEOUT_SECONDS = 1800  # 30 minutes
DEFAULT_ABSOLUTE_TIMEOUT_SECONDS = 43200  # 12 hours
SESSION_COOKIE_NAME = "finpilot_session"
CSRF_COOKIE_NAME = "finpilot_csrf"


def _to_utc(dt: datetime) -> datetime:
    """Ensure datetime is UTC-aware even when loaded from naive SQLite column."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class SessionManager:
    """Manages secure opaque server-side sessions stored in database."""

    def __init__(
        self,
        idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS,
        absolute_timeout_seconds: int = DEFAULT_ABSOLUTE_TIMEOUT_SECONDS,
    ) -> None:
        self.idle_timeout_seconds = idle_timeout_seconds
        self.absolute_timeout_seconds = absolute_timeout_seconds

    @staticmethod
    def hash_session_token(token: str) -> str:
        """Compute deterministic SHA-256 hash of opaque session token."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_session(
        self,
        db: DBSession,
        user: User,
        ip_address: str | None = None,
        user_agent: str | None = None,
        now: datetime | None = None,
    ) -> tuple[str, UserSession]:
        """Create a new opaque server-side session.

        Returns tuple of (raw_opaque_token, db_session_record).
        The raw token is returned to be set in an HttpOnly cookie, and NEVER stored in DB.
        """
        now_utc = now or datetime.now(UTC)
        raw_token = secrets.token_urlsafe(32)
        token_hash = self.hash_session_token(raw_token)
        abs_expiry = now_utc + timedelta(seconds=self.absolute_timeout_seconds)

        session_record = UserSession(
            session_id_hash=token_hash,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent[:255] if user_agent else None,
            idle_timeout_seconds=self.idle_timeout_seconds,
            absolute_timeout_seconds=self.absolute_timeout_seconds,
            is_revoked=False,
            last_active_at=now_utc,
            expires_at=abs_expiry,
            created_at=now_utc,
        )
        db.add(session_record)
        db.commit()
        db.refresh(session_record)
        return raw_token, session_record

    def validate_session(
        self,
        db: DBSession,
        raw_token: str,
        now: datetime | None = None,
    ) -> tuple[UserSession, User] | None:
        """Validate an opaque session token.

        Checks:
        1. Token hash exists in database.
        2. Session is not revoked.
        3. Absolute timeout has not elapsed.
        4. Idle timeout has not elapsed.
        5. User is active.

        If valid, updates `last_active_at` timestamp.
        """
        if not raw_token or len(raw_token.strip()) < 16:
            return None

        token_hash = self.hash_session_token(raw_token)
        now_utc = now or datetime.now(UTC)

        stmt = (
            select(UserSession, User)
            .join(User, UserSession.user_id == User.id)
            .where(UserSession.session_id_hash == token_hash)
        )
        result = db.execute(stmt).first()
        if not result:
            return None

        user_session, user = result

        # 1. Check revocation
        if user_session.is_revoked:
            return None

        # 2. Check user active status
        if not user.is_active:
            return None

        # 3. Check absolute timeout
        expires_at = _to_utc(user_session.expires_at)
        if now_utc >= expires_at:
            return None

        # 4. Check idle timeout
        last_active = _to_utc(user_session.last_active_at)
        idle_limit = last_active + timedelta(seconds=user_session.idle_timeout_seconds)
        if now_utc > idle_limit:
            return None

        # Session is valid: update activity timestamp
        user_session.last_active_at = now_utc
        db.commit()
        return user_session, user

    def rotate_session(
        self,
        db: DBSession,
        old_raw_token: str,
        user: User,
        ip_address: str | None = None,
        user_agent: str | None = None,
        now: datetime | None = None,
    ) -> str:
        """Rotate session ID on login or privilege elevation.

        Revokes old session and creates a fresh session with a new opaque token.
        """
        self.revoke_session(db, old_raw_token)
        new_token, _ = self.create_session(
            db=db,
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            now=now,
        )
        return new_token

    def revoke_session(self, db: DBSession, raw_token: str) -> bool:
        """Immediately revoke a session by its raw token."""
        token_hash = self.hash_session_token(raw_token)
        stmt = (
            update(UserSession)
            .where(UserSession.session_id_hash == token_hash)
            .values(is_revoked=True)
        )
        result = cast(CursorResult[Any], db.execute(stmt))
        db.commit()
        return bool(result.rowcount > 0)

    def revoke_all_user_sessions(self, db: DBSession, user_id: int) -> int:
        """Revoke all active sessions for a user (called on password change or security events)."""
        stmt = (
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.is_revoked.is_(False))
            .values(is_revoked=True)
        )
        result = cast(CursorResult[Any], db.execute(stmt))
        db.commit()
        return int(result.rowcount)
