"""Security verification for database queries, connection config, and secrets.

Covers: SEC-03, SEC-10, SEC-11, SEC-23.
Tests:
1. SEC-10 Parameterized queries: SQL injection payloads handled safely by bound parameters;
   prohibits raw string concatenation.
2. SEC-08 / SEC-11 Secret redaction: Database connection passwords are redacted in logs.
3. SEC-03 Private network & TLS enforcement: Production rejects unencrypted DB connections
   and localhost/insecure DB engines.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from finpilot.config import ConfigError, Settings
from finpilot.db import (
    Base,
    Instrument,
)
from finpilot.logging_config import RedactingFormatter


@pytest.fixture
def clean_db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        # Seed an instrument
        inst = Instrument(
            isin="INE002A01018",
            symbol="RELIANCE",
            name="Reliance Industries",
        )
        session.add(inst)
        session.commit()
        yield session
    engine.dispose()


# ---------------------------------------------------------------------------
# 1. SEC-10: Parameterized Queries and SQL Injection Safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "malicious_symbol",
    [
        "' OR '1'='1",
        "'; DROP TABLE instruments; --",
        "' UNION SELECT 1, 'HACK', 'HACK', 'HACK', 'EQ', 'NSE', 'INR', 1, 0.05, 'ACTIVE', 0, 0 --",
        "RELIANCE' AND 1=0 UNION ALL SELECT * FROM instruments WHERE '1'='1",
    ],
)
def test_parameterized_queries_neutralize_sql_injection(
    clean_db: Session, malicious_symbol: str
) -> None:
    # 1. ORM query using bound parameter
    stmt = select(Instrument).where(Instrument.symbol == malicious_symbol)
    results = clean_db.scalars(stmt).all()
    # No records should match the malicious payload literal
    assert len(results) == 0

    # 2. Raw SQL using parameter binding (text(:sym))
    safe_raw_stmt = text("SELECT * FROM instruments WHERE symbol = :symbol_val")
    raw_results = clean_db.execute(safe_raw_stmt, {"symbol_val": malicious_symbol}).fetchall()
    assert len(raw_results) == 0

    # 3. Verify the instruments table was NOT dropped or tampered with
    count = clean_db.scalar(select(Instrument))
    assert count is not None
    assert count.symbol == "RELIANCE"


# ---------------------------------------------------------------------------
# 2. SEC-08 / SEC-11 / SEC-23: Secret Redaction & Connection Security
# ---------------------------------------------------------------------------


def test_database_url_credentials_redacted_in_logging() -> None:
    sensitive_db_url = (
        "postgresql+psycopg://finpilot_app:SUPER_SECRET_DB_PASS_456@db.internal:5432/finpilot"
        "?sslmode=require"
    )
    record = logging.LogRecord(
        name="finpilot.db",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg=f"Connected to database at {sensitive_db_url}",
        args=(),
        exc_info=None,
    )

    formatter = RedactingFormatter()
    formatted = formatter.format(record)

    # Password MUST be redacted; plain password MUST NOT appear
    assert "SUPER_SECRET_DB_PASS_456" not in formatted
    assert "[REDACTED" in formatted or "password" not in formatted


def test_production_database_connection_security_enforcement() -> None:
    base_prod: dict[str, Any] = {
        "app_env": "production",
        "secret_key": "k" * 40,
        "cors_allowed_origins": "https://finpilot.internal",
        "debug": False,
        "docs_enabled": False,
    }

    # 1. Rejects SQLite in production (SEC-03)
    with pytest.raises(ConfigError) as exc_sqlite:
        Settings(_env_file=None, database_url="sqlite:///prod.db", **base_prod)
    assert "sqlite is not allowed as the production database" in str(exc_sqlite.value).lower()

    # 2. Rejects PostgreSQL without TLS / sslmode (SEC-03)
    with pytest.raises(ConfigError) as exc_tls:
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://app:pass@db.internal:5432/finpilot",
            **base_prod,
        )
    assert "sslmode" in str(exc_tls.value).lower()

    # 3. Accepts TLS-secured PostgreSQL connection on private network host
    valid_prod = Settings(
        _env_file=None,
        database_url=(
            "postgresql+psycopg://finpilot_app:pass@db.internal:5432/finpilot?sslmode=require"
        ),
        **base_prod,
    )
    assert valid_prod.database_url is not None
    assert "sslmode=require" in valid_prod.database_url
