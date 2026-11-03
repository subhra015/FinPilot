"""API Authentication, Authorization, IDOR, CSRF, and Audit Ledger acceptance tests (Layer 12 Gate).

Governed by:
- OWASP API Security Top 10 (API1: BOLA/IDOR, API2: Broken Auth, API5: Broken Function Level Auth)
- NIST SP 800-63B-4
- SECURITY_CHECKLIST.md SEC-01, SEC-02, SEC-05, SEC-06, SEC-08, SEC-09, SEC-10, SEC-11,
  SEC-12, SEC-15, SEC-16, SEC-17, SEC-24
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from finpilot.app import create_app
from finpilot.auth.csrf import generate_csrf_token
from finpilot.auth.sessions import SessionManager
from finpilot.db import Base
from finpilot.db.enums import UserRole
from finpilot.db.models import Account, Portfolio, User


def _setup_test_client(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
) -> tuple[TestClient, Session]:
    """Create test client with a persistent temporary SQLite database for the test."""
    db_file = tmp_path_factory.mktemp("db") / "test_api_auth.db"
    db_url = f"sqlite+pysqlite:///{db_file}"

    engine = create_engine(db_url, future=True)
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
    Base.metadata.create_all(engine)

    settings = make_settings(
        database_url=db_url,
        secret_key="a" * 64,
        cors_allowed_origins="http://localhost:3000",
    )
    app = create_app(settings)
    client = TestClient(app, base_url="http://localhost:3000")

    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    return client, session


def test_unauthenticated_requests_rejected(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
):
    """Private endpoints must reject unauthenticated requests with 401 Unauthorized."""
    client, _ = _setup_test_client(make_settings, tmp_path_factory)

    # 1. Accounts
    resp = client.get("/api/accounts")
    assert resp.status_code == 401
    assert "error" in resp.json()

    # 2. Portfolios
    resp = client.get("/api/portfolios")
    assert resp.status_code == 401

    # 3. Ledger
    resp = client.get("/api/ledger/events")
    assert resp.status_code == 401

    # 4. Risk
    resp = client.get("/api/risk/config")
    assert resp.status_code == 401

    # 5. Models
    resp = client.get("/api/models")
    assert resp.status_code == 401


def test_user_registration_login_logout_flow(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
):
    """Complete registration, login, authenticated session, and logout lifecycle."""
    client, db = _setup_test_client(make_settings, tmp_path_factory)

    # 1. Register new user with NIST-compliant password (>=15 chars)
    reg_payload = {
        "email": "trader@finpilot.test",
        "password": "correct-horse-battery-staple-2026",
        "role": "USER",
    }
    resp_reg = client.post("/api/auth/register", json=reg_payload)
    assert resp_reg.status_code == 201
    reg_data = resp_reg.json()
    assert reg_data["email"] == "trader@finpilot.test"
    assert reg_data["role"] == "USER"

    # 2. Verify Argon2id hash is stored and plaintext password is NOT in database
    db_user = db.execute(select(User).where(User.email == "trader@finpilot.test")).scalar_one()
    assert db_user.password_hash.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert "correct-horse-battery-staple-2026" not in db_user.password_hash

    # 3. Login to establish session
    login_payload = {
        "email": "trader@finpilot.test",
        "password": "correct-horse-battery-staple-2026",
    }
    resp_login = client.post("/api/auth/login", json=login_payload)
    assert resp_login.status_code == 200

    # Cookies must be set
    assert "finpilot_session" in client.cookies
    assert "finpilot_csrf" in client.cookies
    csrf_token = client.cookies["finpilot_csrf"]

    # 4. Access authenticated /api/auth/me
    resp_me = client.get("/api/auth/me")
    assert resp_me.status_code == 200
    assert resp_me.json()["email"] == "trader@finpilot.test"

    # 5. Logout
    resp_logout = client.post(
        "/api/auth/logout",
        headers={"x-csrf-token": csrf_token, "origin": "http://localhost:3000"},
    )
    assert resp_logout.status_code == 200

    # 6. Attempt accessing /me after logout must fail
    resp_after = client.get("/api/auth/me")
    assert resp_after.status_code == 401


def test_cross_user_idor_protection(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
):
    """User A must NOT be able to view or manipulate User B's accounts or portfolios (SEC-06)."""
    client, db = _setup_test_client(make_settings, tmp_path_factory)

    # Register User A
    client.post(
        "/api/auth/register",
        json={
            "email": "usera@finpilot.test",
            "password": "passphrase-for-user-a-2026",
            "role": "USER",
        },
    )

    # Register User B
    client.post(
        "/api/auth/register",
        json={
            "email": "userb@finpilot.test",
            "password": "passphrase-for-user-b-2026",
            "role": "USER",
        },
    )
    user_b = db.execute(select(User).where(User.email == "userb@finpilot.test")).scalar_one()

    # Create account and portfolio for User B in the database
    account_b = Account(
        user_id=user_b.id,
        account_number="ACC-USER-B-001",
        name="User B Trading Account",
    )
    db.add(account_b)
    db.commit()
    db.refresh(account_b)

    portfolio_b = Portfolio(
        account_id=account_b.id,
        name="User B Portfolio",
    )
    db.add(portfolio_b)
    db.commit()
    db.refresh(portfolio_b)

    # Login as User A
    client.post(
        "/api/auth/login",
        json={"email": "usera@finpilot.test", "password": "passphrase-for-user-a-2026"},
    )

    # User A attempts to view User B's account by ID (IDOR attack)
    resp_idor_acc = client.get(f"/api/accounts/{account_b.id}")
    assert resp_idor_acc.status_code == 403
    assert "Access denied" in resp_idor_acc.json()["error"]

    # User A attempts to view User B's portfolio by ID (IDOR attack)
    resp_idor_port = client.get(f"/api/portfolios/{portfolio_b.id}")
    assert resp_idor_port.status_code == 403
    assert "Access denied" in resp_idor_port.json()["error"]


def test_non_admin_cannot_access_admin_risk_routes(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
):
    """Regular user cannot access admin-only risk controls (SEC-01, SEC-09)."""
    client, db = _setup_test_client(make_settings, tmp_path_factory)

    # Register standard user
    client.post(
        "/api/auth/register",
        json={
            "email": "regular@finpilot.test",
            "password": "passphrase-regular-trader-2026",
            "role": "USER",
        },
    )
    # Login as standard user
    client.post(
        "/api/auth/login",
        json={"email": "regular@finpilot.test", "password": "passphrase-regular-trader-2026"},
    )
    csrf_token = client.cookies.get("finpilot_csrf", "")

    # Attempt to activate emergency kill switch
    resp = client.post(
        "/api/risk/kill-switch",
        json={"reason": "Attacker trying to trigger kill switch", "action": "ENGAGE"},
        headers={"x-csrf-token": csrf_token, "origin": "http://localhost:3000"},
    )
    assert resp.status_code == 403
    assert "administrator role required" in resp.json()["error"]


def test_csrf_token_required_for_state_changing_requests(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
):
    """Mutating state-changing requests without valid CSRF token are blocked with 403 (SEC-15)."""
    client, db = _setup_test_client(make_settings, tmp_path_factory)

    # Register admin user directly in DB with MFA active
    admin_user = User(
        user_id="USR-ADMIN01",
        email="admin@finpilot.test",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$dummyhash",
        role=UserRole.ADMIN.value,
        is_active=True,
        mfa_enabled=True,
    )
    db.add(admin_user)
    db.commit()

    # Log in as admin (mock login session directly)
    manager = SessionManager()
    raw_token, session_rec = manager.create_session(db, admin_user)
    client.cookies.set("finpilot_session", raw_token)

    # 1. Attempt POST without x-csrf-token header
    resp_no_csrf = client.post(
        "/api/risk/kill-switch",
        json={"reason": "Testing CSRF requirement", "action": "ENGAGE"},
        headers={"origin": "http://localhost:3000"},
    )
    assert resp_no_csrf.status_code == 403
    assert "CSRF" in resp_no_csrf.json()["error"]

    # 2. Attempt POST with forged x-csrf-token
    resp_bad_csrf = client.post(
        "/api/risk/kill-switch",
        json={"reason": "Testing CSRF requirement", "action": "ENGAGE"},
        headers={"x-csrf-token": "bad-forged-csrf-token", "origin": "http://localhost:3000"},
    )
    assert resp_bad_csrf.status_code == 403

    # 3. Attempt POST with cross-origin (evil-site)
    valid_csrf = generate_csrf_token(session_rec.session_id_hash, "a" * 64)
    resp_evil_origin = client.post(
        "/api/risk/kill-switch",
        json={"reason": "Testing CSRF requirement", "action": "ENGAGE"},
        headers={"x-csrf-token": valid_csrf, "origin": "https://evil-attacker.example.com"},
    )
    assert resp_evil_origin.status_code == 403


def test_sql_injection_defense_via_parameterized_queries(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
):
    """SQL injection payloads must not alter query logic or leak syntax errors."""
    client, db = _setup_test_client(make_settings, tmp_path_factory)

    # Register and login user
    client.post(
        "/api/auth/register",
        json={
            "email": "sqli_test@finpilot.test",
            "password": "passphrase-sqli-test-2026",
            "role": "USER",
        },
    )
    client.post(
        "/api/auth/login",
        json={"email": "sqli_test@finpilot.test", "password": "passphrase-sqli-test-2026"},
    )

    # Injection in path parameter (e.g. integer ID)
    resp_path = client.get("/api/accounts/1' OR '1'='1")
    assert resp_path.status_code == 422  # Rejected by FastAPI integer schema validation

    # Injection in query parameters
    resp_query = client.get("/api/ledger/events?event_type=' OR '1'='1;--")
    # Clean response (empty list or validation error, NEVER database 500 syntax error)
    assert resp_query.status_code in (200, 422)
    if resp_query.status_code == 200:
        assert resp_query.json() == []
