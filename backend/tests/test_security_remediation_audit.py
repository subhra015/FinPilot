"""Comprehensive security regression and remediation verification suite.

Governed by:
- SECURITY_CHECKLIST.md SEC-01 through SEC-27
- Mandatory pre-Layer 15 Project-Wide Security Audit
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from finpilot.app import create_app
from finpilot.auth.csrf import generate_csrf_token
from finpilot.auth.passwords import hash_password
from finpilot.auth.service import AuthService
from finpilot.auth.sessions import SessionManager
from finpilot.config import ConfigError, Settings
from finpilot.db import create_engine_from_settings, create_session_factory
from finpilot.db.base import Base
from finpilot.db.enums import DataMode, LedgerEventType, UserRole
from finpilot.db.models import Account, Instrument, LedgerEvent, PasswordResetToken, Portfolio, User
from finpilot.ledger import AuditLedgerService, LedgerEventPayload
from finpilot.schemas.errors import DomainValidationError, PermissionDeniedError


def _setup_test_client(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
    email_enabled: bool = False,
) -> tuple[TestClient, DBSession, Settings]:
    db_path = tmp_path_factory.mktemp("sec_audit_db") / "test_sec.db"
    settings = make_settings(
        database_url=f"sqlite:///{db_path}",
        cors_allowed_origins="http://localhost:3000",
        secret_key="a" * 64,
        debug=False,
    )
    engine = create_engine_from_settings(settings)
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)

    db = session_factory()
    inst = Instrument(
        id=1,
        isin="INE467B01029",
        symbol="TCS",
        name="Tata Consultancy Services Ltd",
        market="EQUITY",
        exchange="NSE",
        currency="INR",
        tick_size=Decimal("0.05"),
        lot_size=1,
        status="ACTIVE",
    )
    db.add(inst)
    db.commit()

    app = create_app(settings)
    app.state.db_factory = session_factory

    # Inject configured auth service if email_enabled is desired
    if email_enabled:
        from finpilot.api.auth_router import auth_service
        auth_service.email_enabled = True

    client = TestClient(app, base_url="http://localhost:3000", raise_server_exceptions=False)
    return client, db, settings


# ==============================================================================
# SEC-17: Password Reset Expiry, Single-Use & Session Invalidation Tests
# ==============================================================================

def test_password_reset_anti_enumeration_when_email_disabled(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
) -> None:
    """When email infrastructure is unconfigured, generic message returned without revealing account existence."""
    client, db, _ = _setup_test_client(make_settings, tmp_path_factory, email_enabled=False)

    # Request for nonexistent user
    resp_nonexistent = client.post(
        "/api/auth/reset-password-request",
        json={"email": "nonexistent@finpilot.test"},
    )
    assert resp_nonexistent.status_code == 200
    msg1 = resp_nonexistent.json()["message"]
    assert "If the account exists" in msg1

    # Register user
    client.post(
        "/api/auth/register",
        json={
            "email": "existing@finpilot.test",
            "password": "valid-passphrase-2026-secure",
            "role": "USER",
        },
    )

    # Request for existing user
    resp_existing = client.post(
        "/api/auth/reset-password-request",
        json={"email": "existing@finpilot.test"},
    )
    assert resp_existing.status_code == 200
    msg2 = resp_existing.json()["message"]
    assert msg1 == msg2, "Generic response must be identical to mitigate user enumeration"


def test_password_reset_token_expiry_enforcement(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
) -> None:
    """Tokens older than 15 minutes must be rejected with PermissionDeniedError."""
    _, db, _ = _setup_test_client(make_settings, tmp_path_factory, email_enabled=True)
    auth = AuthService(email_enabled=True)

    user = auth.register_user(
        db,
        email="expiry_test@finpilot.test",
        password="valid-passphrase-2026-secure",
    )

    # Issue reset token manually in the past (> 15 minutes expired)
    raw_token = "expired_test_token_1234567890abcdef"
    token_hash = SessionManager.hash_session_token(raw_token)
    now_utc = datetime.now(UTC)

    expired_record = PasswordResetToken(
        token_hash=token_hash,
        user_id=user.id,
        expires_at=now_utc - timedelta(minutes=5),  # Already expired
        is_used=False,
        created_at=now_utc - timedelta(minutes=20),
    )
    db.add(expired_record)
    db.commit()

    with pytest.raises(PermissionDeniedError) as exc:
        auth.confirm_password_reset(
            db,
            raw_reset_token=raw_token,
            new_password="new-secure-passphrase-2026!",
        )
    assert "invalid or expired" in str(exc.value).lower()


def test_password_reset_single_use_behavior(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
) -> None:
    """A reset token cannot be reused once consumed; second attempt must fail."""
    _, db, _ = _setup_test_client(make_settings, tmp_path_factory, email_enabled=True)
    auth = AuthService(email_enabled=True)

    user = auth.register_user(
        db,
        email="single_use_test@finpilot.test",
        password="valid-passphrase-2026-secure",
    )

    raw_token = "single_use_test_token_abcdef123456"
    token_hash = SessionManager.hash_session_token(raw_token)
    now_utc = datetime.now(UTC)

    record = PasswordResetToken(
        token_hash=token_hash,
        user_id=user.id,
        expires_at=now_utc + timedelta(minutes=15),
        is_used=False,
        created_at=now_utc,
    )
    db.add(record)
    db.commit()

    # First reset succeeds
    success = auth.confirm_password_reset(
        db,
        raw_reset_token=raw_token,
        new_password="new-secure-passphrase-attempt-1!",
    )
    assert success is True

    # Check record is_used is True in DB
    refreshed = db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)).scalar_one()
    assert refreshed.is_used is True

    # Replay attack: second reset attempt with the same token MUST fail
    with pytest.raises(PermissionDeniedError) as exc:
        auth.confirm_password_reset(
            db,
            raw_reset_token=raw_token,
            new_password="attacker-passphrase-attempt-2!",
        )
    assert "invalid or expired" in str(exc.value).lower()


def test_password_reset_revokes_all_active_sessions(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
) -> None:
    """Upon successful password reset, all outstanding active sessions for the user are immediately revoked."""
    client, db, _ = _setup_test_client(make_settings, tmp_path_factory, email_enabled=True)
    auth = AuthService(email_enabled=True)

    # 1. Register and login to create an active session
    client.post(
        "/api/auth/register",
        json={
            "email": "session_revoke_test@finpilot.test",
            "password": "valid-passphrase-2026-secure",
            "role": "USER",
        },
    )
    login_resp = client.post(
        "/api/auth/login",
        json={
            "email": "session_revoke_test@finpilot.test",
            "password": "valid-passphrase-2026-secure",
        },
    )
    assert login_resp.status_code == 200
    session_cookie = client.cookies.get("finpilot_session")
    assert session_cookie is not None

    # Verify session is currently active
    resp_before = client.get("/api/auth/me")
    assert resp_before.status_code == 200

    # 2. Issue and execute password reset
    user = db.execute(select(User).where(User.email == "session_revoke_test@finpilot.test")).scalar_one()
    raw_token = "revoke_sessions_token_999999999999"
    token_hash = SessionManager.hash_session_token(raw_token)
    now_utc = datetime.now(UTC)

    record = PasswordResetToken(
        token_hash=token_hash,
        user_id=user.id,
        expires_at=now_utc + timedelta(minutes=15),
        is_used=False,
        created_at=now_utc,
    )
    db.add(record)
    db.commit()

    auth.confirm_password_reset(
        db,
        raw_reset_token=raw_token,
        new_password="new-updated-passphrase-2026!",
    )

    # 3. Old session MUST now be completely revoked (returns 401 Unauthorized)
    resp_after = client.get("/api/auth/me")
    assert resp_after.status_code == 401
    assert "invalid, expired, or revoked" in resp_after.json()["error"].lower()


# ==============================================================================
# SEC-06, SEC-07, SEC-20: Unhandled Exception & Traceback Sanitization Tests
# ==============================================================================

def test_unhandled_exception_sanitizes_stack_trace_and_paths(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
) -> None:
    """Unhandled server errors must return clean 500 JSON without stack traces or path leakage."""
    client, db, settings = _setup_test_client(make_settings, tmp_path_factory)

    # Add a temporary test route that raises an unhandled exception with internal paths
    app = client.app

    @app.get("/api/test-faulty-route")
    def faulty_route() -> None:
        raise RuntimeError("Fatal database connection failed at D:\\Projects\\FinPilot\\secret.py with SELECT * FROM users")

    resp = client.get("/api/test-faulty-route")
    assert resp.status_code == 500
    data = resp.json()

    # Must adhere to ErrorResponse schema
    assert data["code"] == "INTERNAL_ERROR"
    assert data["error"] == "An unexpected internal server error occurred."

    # Zero leakage of internal filesystem paths, SQL queries, or tracebacks
    resp_text = resp.text
    assert "D:\\Projects" not in resp_text
    assert "Traceback" not in resp_text
    assert "SELECT * FROM" not in resp_text


# ==============================================================================
# SEC-16: CSRF Protection on Mutating Logout and MFA Setup
# ==============================================================================

def test_logout_csrf_protection(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
) -> None:
    """Calling POST /api/auth/logout without CSRF token is rejected with 403."""
    client, db, _ = _setup_test_client(make_settings, tmp_path_factory)

    # Register and login
    client.post(
        "/api/auth/register",
        json={
            "email": "csrf_logout_user@finpilot.test",
            "password": "valid-passphrase-2026-secure",
            "role": "USER",
        },
    )
    client.post(
        "/api/auth/login",
        json={
            "email": "csrf_logout_user@finpilot.test",
            "password": "valid-passphrase-2026-secure",
        },
    )

    # 1. POST logout WITHOUT X-CSRF-Token -> Must return 403 Forbidden
    resp_no_csrf = client.post("/api/auth/logout")
    assert resp_no_csrf.status_code == 403
    assert "CSRF" in resp_no_csrf.json()["error"]

    # 2. POST logout WITH valid X-CSRF-Token -> Must succeed (200)
    csrf_token = client.cookies.get("finpilot_csrf", "")
    resp_valid = client.post(
        "/api/auth/logout",
        headers={"x-csrf-token": csrf_token, "origin": "http://localhost:3000"},
    )
    assert resp_valid.status_code == 200


def test_mfa_setup_csrf_protection(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
) -> None:
    """Calling POST /api/auth/mfa/setup without CSRF token is rejected with 403."""
    client, db, _ = _setup_test_client(make_settings, tmp_path_factory)

    client.post(
        "/api/auth/register",
        json={
            "email": "csrf_mfa_user@finpilot.test",
            "password": "valid-passphrase-2026-secure",
            "role": "USER",
        },
    )
    client.post(
        "/api/auth/login",
        json={
            "email": "csrf_mfa_user@finpilot.test",
            "password": "valid-passphrase-2026-secure",
        },
    )

    # Mutating POST without CSRF token must fail with 403
    resp = client.post("/api/auth/mfa/setup")
    assert resp.status_code == 403
    assert "CSRF" in resp.json()["error"]


# ==============================================================================
# SEC-11 & SEC-20: Production Fail-Closed Configuration Matrix
# ==============================================================================

def test_production_config_rejects_debug_mode() -> None:
    """Production fails closed if debug is enabled."""
    with pytest.raises(ConfigError) as exc:
        Settings(
            _env_file=None,
            app_env="production",
            secret_key="x" * 40,
            database_url="postgresql+psycopg://user:pass@db.internal:5432/finpilot?sslmode=require",
            cors_allowed_origins="https://app.example.com",
            debug=True,
            docs_enabled=False,
        )
    assert "FINPILOT_DEBUG must be false in production" in str(exc.value)


def test_production_config_rejects_sqlite() -> None:
    """Production fails closed if SQLite is used as the database."""
    with pytest.raises(ConfigError) as exc:
        Settings(
            _env_file=None,
            app_env="production",
            secret_key="x" * 40,
            database_url="sqlite:///./prod.db",
            cors_allowed_origins="https://app.example.com",
            debug=False,
            docs_enabled=False,
        )
    assert "SQLite is not allowed as the production database" in str(exc.value)


def test_production_config_rejects_wildcard_cors() -> None:
    """Production fails closed if wildcard CORS origin is specified."""
    with pytest.raises(ConfigError) as exc:
        Settings(
            _env_file=None,
            app_env="production",
            secret_key="x" * 40,
            database_url="postgresql+psycopg://user:pass@db.internal:5432/finpilot?sslmode=require",
            cors_allowed_origins="*",
            debug=False,
            docs_enabled=False,
        )
    assert "wildcard CORS origin is not allowed in production" in str(exc.value)


def test_production_config_rejects_short_secret_key() -> None:
    """Production fails closed if secret key is less than 32 characters."""
    with pytest.raises(ConfigError) as exc:
        Settings(
            _env_file=None,
            app_env="production",
            secret_key="short_secret",
            database_url="postgresql+psycopg://user:pass@db.internal:5432/finpilot?sslmode=require",
            cors_allowed_origins="https://app.example.com",
            debug=False,
            docs_enabled=False,
        )
    assert "FINPILOT_SECRET_KEY must be at least 32 characters" in str(exc.value)


# ==============================================================================
# SEC-08 & SEC-19: Audit Ledger Hash Chaining & Tamper Detection
# ==============================================================================

def test_ledger_detects_payload_tampering(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
) -> None:
    """Tampering with a recorded event's payload invalidates the cryptographic hash chain."""
    _, db, _ = _setup_test_client(make_settings, tmp_path_factory)
    ledger = AuditLedgerService()

    # Record two valid events
    p1 = LedgerEventPayload(
        event_id="EVT-SEC-01",
        event_type=LedgerEventType.DECISION,
        opportunity_id="OPP-01",
        symbol="TCS",
        decision_state="PROPOSED",
        model_id="MODEL-LOGREG-V1",
        policy_version="TP-V1",
        features_snapshot={"rsi": 50.0},
        predicted_probability=0.6,
        calibrated_probability=0.55,
        timestamp=datetime.now(UTC),
    )
    p2 = LedgerEventPayload(
        event_id="EVT-SEC-02",
        event_type=LedgerEventType.DECISION,
        opportunity_id="OPP-02",
        symbol="TCS",
        decision_state="PROPOSED",
        model_id="MODEL-LOGREG-V1",
        policy_version="TP-V1",
        features_snapshot={"rsi": 60.0},
        predicted_probability=0.7,
        calibrated_probability=0.65,
        timestamp=datetime.now(UTC),
    )

    ev1 = ledger.record_event(db, p1)
    ev2 = ledger.record_event(db, p2)

    # Initial chain verification must pass
    res_clean = ledger.replay_ledger(db, mode=DataMode.HISTORICAL_REPLAY, verify_hash_chain=True)
    assert res_clean.chain_verified is True
    assert res_clean.tamper_detected is False

    # Attacker tampers directly with the stored payload in the database
    ev1.payload = json.dumps({"tampered": True, "stolen_cash": 100000})
    db.commit()

    # Replay must now detect tampering and fail validation
    res_tampered = ledger.replay_ledger(db, mode=DataMode.HISTORICAL_REPLAY, verify_hash_chain=True)
    assert res_tampered.is_valid is False
    assert res_tampered.tamper_detected is True
    assert len(res_tampered.tamper_details) > 0
    assert "payload integrity compromised" in res_tampered.tamper_details[0]
