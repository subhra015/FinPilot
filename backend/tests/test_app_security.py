"""HTTP security-default tests (SEC-13, SEC-14, SEC-20)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from finpilot.app import create_app


def test_security_headers_present(
    make_settings: Callable[..., Any],
) -> None:
    client = TestClient(create_app(make_settings()))
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "payment=()" in response.headers["permissions-policy"]


def test_hsts_absent_outside_production(
    make_settings: Callable[..., Any],
) -> None:
    client = TestClient(create_app(make_settings()))
    assert "strict-transport-security" not in client.get("/healthz").headers


def test_hsts_present_in_production() -> None:
    from finpilot.config import Settings

    settings = Settings(
        _env_file=None,
        app_env="production",
        secret_key="x" * 40,
        database_url="postgresql+psycopg://user:pass@db.internal:5432/finpilot?sslmode=require",
        cors_allowed_origins="https://app.example.com",
        debug=False,
        docs_enabled=False,
    )
    client = TestClient(create_app(settings))
    response = client.get("/healthz")
    assert "strict-transport-security" in response.headers


def test_docs_disabled_when_not_enabled(
    make_settings: Callable[..., Any],
) -> None:
    client = TestClient(create_app(make_settings(docs_enabled=False)))
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_cors_allows_only_explicit_origins(
    make_settings: Callable[..., Any],
) -> None:
    app = create_app(make_settings(cors_allowed_origins="http://localhost:5173"))
    client = TestClient(app)

    allowed = client.get("/healthz", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"

    denied = client.get("/healthz", headers={"Origin": "http://evil.example"})
    assert denied.headers.get("access-control-allow-origin") != "*"
    assert denied.headers.get("access-control-allow-origin") != "http://evil.example"
