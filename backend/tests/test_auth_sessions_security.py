"""Session management security tests (SEC-15, Layer 12).

Governed by:
- OWASP Session Management Cheat Sheet
- SECURITY_CHECKLIST.md SEC-15
- Layer 12 Gate: Opaque server-side sessions, SHA-256 hashed storage, idle/absolute timeouts,
  rotation, instant revocation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from finpilot.auth.sessions import (
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    SessionManager,
)
from finpilot.db.enums import UserRole
from finpilot.db.models import User, UserSession


def _create_test_user(db: DBSession, email: str = "trader@finpilot.test") -> User:
    user = User(
        user_id="USR-TEST01",
        email=email,
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$dummyhash",
        role=UserRole.USER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_session_creation_stores_only_hash(db_session: DBSession):
    """Raw session token must NEVER be stored in plaintext in the database."""
    manager = SessionManager()
    user = _create_test_user(db_session, "user1@finpilot.test")

    raw_token, session_record = manager.create_session(
        db=db_session,
        user=user,
        ip_address="127.0.0.1",
        user_agent="pytest/test-agent",
    )

    # Raw token is high entropy (at least 32 characters)
    assert len(raw_token) >= 32
    assert raw_token != session_record.session_id_hash

    # Query database directly to confirm raw token is NOT in DB
    db_record = db_session.execute(
        select(UserSession).where(UserSession.session_id_hash == session_record.session_id_hash)
    ).scalar_one()

    assert db_record.session_id_hash == manager.hash_session_token(raw_token)
    # The raw token itself does not appear in any column of UserSession
    assert raw_token not in str(db_record.__dict__)


def test_session_validation_active(db_session: DBSession):
    """Valid unexpired session returns user and session record."""
    manager = SessionManager()
    user = _create_test_user(db_session, "user2@finpilot.test")

    raw_token, _ = manager.create_session(
        db=db_session,
        user=user,
    )

    validated = manager.validate_session(db_session, raw_token)
    assert validated is not None
    validated_session, validated_user = validated
    assert validated_user.id == user.id
    assert validated_session.is_revoked is False


def test_session_idle_timeout_expiration(db_session: DBSession):
    """Sessions inactive for longer than idle_timeout_seconds must be rejected."""
    manager = SessionManager(idle_timeout_seconds=60)  # 60s idle timeout
    user = _create_test_user(db_session, "user3@finpilot.test")

    raw_token, session_record = manager.create_session(db=db_session, user=user)

    # Artificially age the last_seen_at past the 60s idle threshold
    session_record.last_active_at = datetime.now(UTC) - timedelta(seconds=70)
    db_session.commit()

    validated = manager.validate_session(db_session, raw_token)
    assert validated is None


def test_session_absolute_timeout_expiration(db_session: DBSession):
    """Sessions older than absolute_timeout_seconds must be rejected even if recently active."""
    manager = SessionManager(
        idle_timeout_seconds=DEFAULT_IDLE_TIMEOUT_SECONDS,
        absolute_timeout_seconds=3600,  # 1 hour absolute
    )
    user = _create_test_user(db_session, "user4@finpilot.test")

    raw_token, session_record = manager.create_session(db=db_session, user=user)

    # Artificially age created_at and expires_at past 1 hour, but keep last_active_at fresh
    session_record.created_at = datetime.now(UTC) - timedelta(hours=2)
    session_record.expires_at = datetime.now(UTC) - timedelta(hours=1)
    session_record.last_active_at = datetime.now(UTC)
    db_session.commit()

    validated = manager.validate_session(db_session, raw_token)
    assert validated is None


def test_session_rotation(db_session: DBSession):
    """Session rotation revokes old token and issues a new valid token."""
    manager = SessionManager()
    user = _create_test_user(db_session, "user5@finpilot.test")

    old_raw_token, _ = manager.create_session(db=db_session, user=user)

    # Rotate session
    new_raw_token = manager.rotate_session(db_session, old_raw_token, user)
    assert new_raw_token != old_raw_token

    # Old token is now invalid / revoked
    assert manager.validate_session(db_session, old_raw_token) is None

    # New token is active
    val_new = manager.validate_session(db_session, new_raw_token)
    assert val_new is not None
    _, u_new = val_new
    assert u_new.id == user.id


def test_session_revocation(db_session: DBSession):
    """Single session revocation immediately invalidates access."""
    manager = SessionManager()
    user = _create_test_user(db_session, "user6@finpilot.test")

    raw_token, _ = manager.create_session(db=db_session, user=user)

    revoked = manager.revoke_session(db_session, raw_token)
    assert revoked is True

    # Subsequent validation fails
    assert manager.validate_session(db_session, raw_token) is None


def test_bulk_user_sessions_revocation(db_session: DBSession):
    """Revoking all sessions for a user invalidates all active tokens (e.g. on reset)."""
    manager = SessionManager()
    user = _create_test_user(db_session, "user7@finpilot.test")

    token1, _ = manager.create_session(db=db_session, user=user)
    token2, _ = manager.create_session(db=db_session, user=user)

    revoked_count = manager.revoke_all_user_sessions(db_session, user.id)
    assert revoked_count == 2

    assert manager.validate_session(db_session, token1) is None
    assert manager.validate_session(db_session, token2) is None
