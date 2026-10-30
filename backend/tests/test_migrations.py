"""Migration reversibility test (SEC-03): upgrade then downgrade cleanly."""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    cfg.set_main_option("prepend_sys_path", str(BACKEND_ROOT / "src"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return cfg


def _tables(db_path: Path) -> list[str]:
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        return sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_migration_upgrade_then_downgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "migration.db"
    cfg = _alembic_config(db_path)

    command.upgrade(cfg, "head")
    assert "schema_meta" in _tables(db_path)

    command.downgrade(cfg, "base")
    assert "schema_meta" not in _tables(db_path)
