"""Configuration validation tests (SEC-11, SEC-20)."""

from __future__ import annotations

from typing import Any

import pytest

from finpilot.config import AppEnv, ConfigError, Settings, load_settings


def _production(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "app_env": "production",
        "secret_key": "x" * 40,
        "database_url": "postgresql+psycopg://user:pass@db.internal:5432/finpilot?sslmode=require",
        "cors_allowed_origins": "https://app.example.com",
        "debug": False,
        "docs_enabled": False,
    }
    base.update(overrides)
    return base


def test_development_defaults_are_localhost_and_documented() -> None:
    settings = Settings(_env_file=None, app_env="development")
    assert settings.host == "127.0.0.1"
    assert settings.database_url is not None and settings.database_url.startswith("sqlite")
    assert settings.docs_enabled is True
    assert settings.is_production is False
    assert settings.cors_origins == ("http://127.0.0.1:5173", "http://localhost:5173")


def test_test_environment_is_isolated_sqlite_without_cors() -> None:
    settings = Settings(_env_file=None, app_env="test")
    assert settings.database_url is not None and settings.database_url.startswith("sqlite")
    assert settings.cors_origins == ()
    assert settings.docs_enabled is False


def test_valid_production_configuration_loads() -> None:
    settings = Settings(_env_file=None, **_production())
    assert settings.app_env is AppEnv.production
    assert settings.is_production is True
    assert settings.docs_enabled is False


@pytest.mark.parametrize(
    ("overrides", "needle"),
    [
        ({"secret_key": None}, "secret_key"),
        ({"secret_key": "short"}, "secret_key"),
        ({"debug": True}, "debug"),
        ({"docs_enabled": True}, "docs_enabled"),
        ({"cors_allowed_origins": ""}, "cors"),
        ({"cors_allowed_origins": "*"}, "wildcard"),
        ({"cors_allowed_origins": "http://app.example.com"}, "https"),
        ({"database_url": "sqlite:///prod.db"}, "sqlite"),
        ({"database_url": "postgresql+psycopg://user:pass@db.internal:5432/finpilot"}, "tls"),
    ],
)
def test_production_fails_closed(overrides: dict[str, Any], needle: str) -> None:
    with pytest.raises(ConfigError) as excinfo:
        Settings(_env_file=None, **_production(**overrides))
    assert needle in str(excinfo.value).lower()


def test_production_without_any_overrides_fails_closed() -> None:
    with pytest.raises(ConfigError):
        Settings(_env_file=None, app_env="production")


def test_test_environment_rejects_shared_database() -> None:
    with pytest.raises(ConfigError) as excinfo:
        Settings(
            _env_file=None,
            app_env="test",
            database_url="postgresql+psycopg://user:pass@db.internal:5432/finpilot",
        )
    assert "sqlite" in str(excinfo.value).lower()


def test_load_settings_wraps_validation_errors() -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_settings(_env_file=None, app_env="staging")
    assert "validation" in str(excinfo.value).lower()


def test_environments_do_not_share_insecure_defaults() -> None:
    dev = Settings(_env_file=None, app_env="development")
    prod = Settings(_env_file=None, **_production())

    assert dev.debug is False
    assert dev.docs_enabled is not prod.docs_enabled
    assert dev.database_url != prod.database_url
    assert dev.cors_origins != prod.cors_origins
