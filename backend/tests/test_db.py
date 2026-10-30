"""Database engine/session helper tests (SEC-03, SEC-10 foundation)."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import text

from finpilot.config import Settings
from finpilot.db import create_engine_from_settings, create_session_factory


def test_engine_and_session_factory_work_against_isolated_sqlite(
    make_settings: Callable[..., Settings],
) -> None:
    settings = make_settings()
    engine = create_engine_from_settings(settings)
    factory = create_session_factory(engine)

    try:
        assert str(engine.url).startswith("sqlite")
        with factory() as session:
            assert session.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()
