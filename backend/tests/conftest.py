"""Shared pytest fixtures for the backend foundation tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from finpilot.auth.rate_limiter import limiter
from finpilot.config import Settings
from finpilot.db import Base


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> None:
    """Reset sliding window rate limiter buckets between tests."""
    limiter.reset()


@pytest.fixture
def db_session() -> Session:
    """Create a clean in-memory database with SQLite foreign keys enabled."""
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with session_factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def make_settings() -> Callable[..., Settings]:
    """Return a factory building isolated ``test``-environment settings."""

    def _make(**overrides: Any) -> Settings:
        base: dict[str, Any] = {
            "app_env": "test",
            "debug": False,
            "docs_enabled": False,
            "secret_key": None,
            "cors_allowed_origins": "",
            "database_url": "sqlite+pysqlite:///:memory:",
        }
        base.update(overrides)
        return Settings(_env_file=None, **base)

    return _make
