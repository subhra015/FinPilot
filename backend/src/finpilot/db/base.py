"""Typed SQLAlchemy engine/session helpers.

Schema changes are applied via Alembic migrations only; no automatic ``create_all``
or silent resets (SEC-03, SEC-10). Local SQLite is bound to a file path; hosted
databases must be TLS-configured and privately reachable (enforced in settings).
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..config import Settings


class Base(DeclarativeBase):
    """Declarative base for future ORM models."""


def create_engine_from_settings(settings: Settings) -> Engine:
    """Create a SQLAlchemy engine for the configured database URL."""

    url = settings.database_url or ""
    if not url:
        raise ValueError("database_url is not configured")

    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(url, connect_args=connect_args, pool_pre_ping=True, future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory bound to ``engine``."""

    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
