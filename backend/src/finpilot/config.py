"""Environment-aware configuration loading with fail-closed production defaults.

Security controls: SEC-02 (no secrets in source), SEC-11 (validate env at
startup, fail closed in production), SEC-20 (no production debug).

The three environments deliberately do NOT share insecure defaults:

* ``development`` — localhost binding, debug allowed, docs enabled, SQLite file.
* ``test``        — isolated in-memory SQLite only, no CORS.
* ``production``  — fails closed unless a strong secret, explicit HTTPS CORS
  origins, ``debug=false``, docs disabled and a TLS database URL are supplied.
"""

from __future__ import annotations

import enum
from typing import Any

from pydantic import SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_DEFAULT_DB = "sqlite:///./finpilot_dev.db"
_TEST_DEFAULT_DB = "sqlite+pysqlite:///:memory:"
_DEV_DEFAULT_CORS = "http://127.0.0.1:5173,http://localhost:5173"

MIN_SECRET_LENGTH = 32


class AppEnv(enum.StrEnum):
    """Supported runtime environments."""

    development = "development"
    test = "test"
    production = "production"


class ConfigError(RuntimeError):
    """Raised when configuration is invalid or insecure for its environment."""


class Settings(BaseSettings):
    """Application settings loaded from ``FINPILOT_*`` environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="FINPILOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: AppEnv = AppEnv.development
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    secret_key: SecretStr | None = None
    database_url: str | None = None
    cors_allowed_origins: str = ""
    log_level: str = "INFO"
    docs_enabled: bool | None = None

    # -- environment-specific defaults (applied before validation) ----------
    @model_validator(mode="before")
    @classmethod
    def _apply_environment_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        raw_env = data.get("app_env", AppEnv.development)
        env = raw_env.value if isinstance(raw_env, AppEnv) else str(raw_env)
        env = env.lower()

        if not data.get("database_url"):
            data["database_url"] = _TEST_DEFAULT_DB if env == "test" else _DEV_DEFAULT_DB

        origins = data.get("cors_allowed_origins")
        if origins is None or origins == "":
            # Development gets a localhost default; test and production must be
            # explicit so production fails closed instead of inheriting a default.
            data["cors_allowed_origins"] = _DEV_DEFAULT_CORS if env == "development" else ""
        elif isinstance(origins, (list, tuple)):
            data["cors_allowed_origins"] = ",".join(str(item) for item in origins)

        if data.get("docs_enabled") is None:
            # Interactive docs are a development convenience only; test and
            # production default to disabled.
            data["docs_enabled"] = env == "development"

        return data

    @model_validator(mode="after")
    def _validate_environment(self) -> Settings:
        if self.app_env is AppEnv.production:
            self._validate_production()
        elif self.app_env is AppEnv.test:
            self._validate_test()
        return self

    def _validate_production(self) -> None:
        problems: list[str] = []

        secret = self.secret_key.get_secret_value() if self.secret_key else ""
        if len(secret) < MIN_SECRET_LENGTH:
            problems.append(f"FINPILOT_SECRET_KEY must be at least {MIN_SECRET_LENGTH} characters")
        if self.debug:
            problems.append("FINPILOT_DEBUG must be false in production")
        if self.docs_enabled:
            problems.append("FINPILOT_DOCS_ENABLED must be false in production")

        origins = self.cors_origins
        if not origins:
            problems.append("FINPILOT_CORS_ALLOWED_ORIGINS must list explicit origins")
        if "*" in origins:
            problems.append("wildcard CORS origin is not allowed in production")
        for origin in origins:
            if not origin.startswith("https://"):
                problems.append(f"production CORS origin must use https: {origin}")

        db_url = self.database_url or ""
        if db_url.startswith("sqlite"):
            problems.append("SQLite is not allowed as the production database")
        elif db_url.startswith("postgresql") and "sslmode" not in db_url:
            problems.append("production PostgreSQL DATABASE_URL must require TLS (sslmode=...)")

        if problems:
            joined = "; ".join(problems)
            raise ConfigError(f"Refusing insecure production configuration: {joined}")

    def _validate_test(self) -> None:
        db_url = self.database_url or ""
        if not db_url.startswith("sqlite"):
            raise ConfigError("test environment must use an isolated SQLite database")

    @property
    def cors_origins(self) -> tuple[str, ...]:
        raw = self.cors_allowed_origins or ""
        return tuple(origin.strip() for origin in raw.split(",") if origin.strip())

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.production


def load_settings(**overrides: Any) -> Settings:
    """Load settings, converting pydantic validation errors into ``ConfigError``.

    Called at application startup so that a malformed or insecure environment
    aborts the process (fail closed) instead of running with partial config.
    """

    try:
        return Settings(**overrides)
    except ValidationError as exc:
        raise ConfigError(f"Configuration validation failed: {exc}") from exc
