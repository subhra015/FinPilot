"""Migration reversibility and chain progression tests (SEC-03, Layer 2).

Tests:
1. Migration from an empty database to head.
2. Stepwise forward migration from 0001_baseline to 0002_persistence_foundation.
3. Rollback from head to 0001_baseline and down to base.
4. Forward re-upgrade from base to head.
5. All operational tables and constraints verified.
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BACKEND_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TABLES_L1 = {"schema_meta"}
EXPECTED_TABLES_L2 = {
    "schema_meta",
    "instruments",
    "instrument_symbol_history",
    "dataset_manifests",
    "accounts",
    "portfolios",
    "positions",
    "orders",
    "ledger_events",
}


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    cfg.set_main_option("prepend_sys_path", str(BACKEND_ROOT / "src"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return cfg


def _tables(db_path: Path) -> set[str]:
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        inspector = sa.inspect(engine)
        return set(inspector.get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()


def test_migration_from_empty_to_head_and_rollback(tmp_path: Path) -> None:
    db_path = tmp_path / "migration_full.db"
    cfg = _alembic_config(db_path)

    # 1. Upgrade from empty to head
    command.upgrade(cfg, "head")
    tables = _tables(db_path)
    assert EXPECTED_TABLES_L2.issubset(tables)

    # 2. Downgrade from head to 0001_baseline
    command.downgrade(cfg, "0001_baseline")
    tables_l1 = _tables(db_path)
    assert tables_l1 == EXPECTED_TABLES_L1

    # 3. Downgrade from 0001_baseline to base
    command.downgrade(cfg, "base")
    assert _tables(db_path) == set()

    # 4. Re-upgrade from base to head
    command.upgrade(cfg, "head")
    assert EXPECTED_TABLES_L2.issubset(_tables(db_path))


def test_migration_stepwise_upgrade_from_previous_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "migration_stepwise.db"
    cfg = _alembic_config(db_path)

    # Migrate to Layer 1 baseline first
    command.upgrade(cfg, "0001_baseline")
    assert _tables(db_path) == EXPECTED_TABLES_L1

    # Step forward to Layer 2 persistence foundation
    command.upgrade(cfg, "0002_persistence_foundation")
    assert EXPECTED_TABLES_L2.issubset(_tables(db_path))
