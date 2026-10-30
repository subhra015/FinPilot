"""Shared pytest fixtures for the backend foundation tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from finpilot.config import Settings


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
