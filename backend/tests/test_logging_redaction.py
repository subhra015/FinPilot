"""Log redaction tests (SEC-08): secrets must never reach log output."""

from __future__ import annotations

import io
import logging

from finpilot.config import Settings
from finpilot.logging_config import configure_logging, redact_text


def _settings(env: str) -> Settings:
    if env == "production":
        return Settings(
            _env_file=None,
            app_env="production",
            secret_key="x" * 40,
            database_url=(
                "postgresql+psycopg://user:pass@db.internal:5432/finpilot?sslmode=require"
            ),
            cors_allowed_origins="https://app.example.com",
            debug=False,
            docs_enabled=False,
            log_level="INFO",
        )
    return Settings(_env_file=None, app_env=env, log_level="INFO")


def test_redact_text_removes_key_value_secrets() -> None:
    out = redact_text("login password=hunter2 token=abc123 api_key=key-456")
    assert "hunter2" not in out
    assert "abc123" not in out
    assert "key-456" not in out
    assert out.count("[REDACTED]") == 3


def test_redact_text_removes_bearer_tokens() -> None:
    out = redact_text("Authorization: Bearer abc.def.ghi")
    assert "abc.def.ghi" not in out
    assert "[REDACTED]" in out


def test_development_logging_redacts_message() -> None:
    stream = io.StringIO()
    configure_logging(_settings("development"), stream=stream)

    logging.getLogger("finpilot.test").info("login password=hunter2 token=abc123")

    out = stream.getvalue()
    assert "hunter2" not in out
    assert "abc123" not in out
    assert "[REDACTED]" in out
    assert "login" in out


def test_production_json_logging_redacts_extra_fields() -> None:
    stream = io.StringIO()
    configure_logging(_settings("production"), stream=stream)

    logging.getLogger("finpilot.test").info(
        "auth",
        extra={"password": "hunter2", "api_key": "key-123", "user": "alice"},
    )

    out = stream.getvalue()
    assert "hunter2" not in out
    assert "key-123" not in out
    assert '"user": "alice"' in out
    assert "[REDACTED]" in out
