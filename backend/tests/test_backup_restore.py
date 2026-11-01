"""Database backup and restore procedure tests in a disposable environment (SEC-03, Layer 2).

Exercises:
1. Online database backup creation and SHA-256 integrity verification.
2. Complete restore into a disposable target environment.
3. Full data verification across instruments, manifests, accounts, orders, and ledger.
4. Tamper detection: corrupted backup artifact fails checksum verification.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from finpilot.db import (
    Account,
    Base,
    DataMode,
    DatasetManifest,
    Instrument,
    InstrumentSymbolHistory,
    LedgerEvent,
    LedgerEventType,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Portfolio,
    Position,
)
from finpilot.db.backup import (
    backup_sqlite_database,
    calculate_file_sha256,
    restore_sqlite_database,
    verify_database_schema,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    cfg.set_main_option("prepend_sys_path", str(BACKEND_ROOT / "src"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return cfg


def test_backup_and_restore_procedure_in_disposable_env(tmp_path: Path) -> None:
    source_db = tmp_path / "source_operational.db"
    backup_file = tmp_path / "backups" / "operational_backup.db"
    target_restored_db = tmp_path / "restored_operational.db"

    # 1. Run migrations on source database to create full Layer 2 schema
    cfg = _alembic_config(source_db)
    command.upgrade(cfg, "head")

    # 2. Populate source database with operational test data
    engine = create_engine(f"sqlite:///{source_db.as_posix()}")
    session_factory = sessionmaker(bind=engine)
    now = datetime.now(UTC)

    saved_port_id: int
    with session_factory() as session:
        # Instrument
        inst = Instrument(
            isin="INE002A01018",
            symbol="RELIANCE",
            name="Reliance Industries Limited",
        )
        session.add(inst)
        session.flush()

        # Symbol history
        hist = InstrumentSymbolHistory(
            instrument_id=inst.id,
            symbol="RELIANCE",
            valid_from=now,
        )
        session.add(hist)

        # Dataset manifest
        manifest = DatasetManifest(
            dataset_name="parquet_historical_candles",
            dataset_version="v1",
            mode=DataMode.HISTORICAL_REPLAY.value,
            provider_source="NSE",
            file_path_or_uri="data/parquet/history.parquet",
            sha256_checksum="f" * 64,
            row_count=10000,
            start_timestamp=now,
            end_timestamp=now,
            schema_version="v1",
        )
        session.add(manifest)

        # Account & Portfolio
        acct = Account(
            account_number="FP-BACKUP-001",
            name="Backup Test Account",
            initial_scenario_capital=Decimal("30000.00"),
            current_cash=Decimal("30000.00"),
        )
        session.add(acct)
        session.flush()

        port = Portfolio(account_id=acct.id, name="Main Portfolio")
        session.add(port)
        session.flush()
        saved_port_id = port.id

        # Position
        pos = Position(
            portfolio_id=port.id,
            instrument_id=inst.id,
            quantity=5,
            average_entry_price=Decimal("2500.00"),
            current_price=Decimal("2520.00"),
        )
        session.add(pos)

        # Order
        ord_item = Order(
            id="ord_backup_test_01",
            portfolio_id=port.id,
            instrument_id=inst.id,
            order_type=OrderType.MARKET.value,
            side=OrderSide.BUY.value,
            quantity=5,
            filled_quantity=5,
            price=Decimal("2500.00"),
            status=OrderStatus.FILLED.value,
        )
        session.add(ord_item)

        # Ledger Event
        payload = '{"test": "backup_integrity"}'
        evt = LedgerEvent(
            sequence_number=1,
            event_id="evt_backup_test_01",
            event_type=LedgerEventType.DECISION.value,
            account_id=acct.id,
            portfolio_id=port.id,
            instrument_id=inst.id,
            mode=DataMode.HISTORICAL_REPLAY.value,
            payload=payload,
            integrity_hash=hashlib.sha256(payload.encode()).hexdigest(),
            timestamp=now,
        )
        session.add(evt)
        session.commit()

    engine.dispose()

    # 3. Perform backup and verify SHA-256
    backup_sha256 = backup_sqlite_database(source_db, backup_file)
    assert backup_file.exists()
    assert len(backup_sha256) == 64
    assert calculate_file_sha256(backup_file) == backup_sha256

    # 4. Restore into a new disposable target environment
    restore_sqlite_database(backup_file, target_restored_db, expected_sha256=backup_sha256)
    assert target_restored_db.exists()

    # 5. Verify restored database schema and contents
    restored_engine = create_engine(f"sqlite:///{target_restored_db.as_posix()}")
    restored_schema = verify_database_schema(restored_engine)
    assert "instruments" in restored_schema
    assert "dataset_manifests" in restored_schema
    assert "accounts" in restored_schema
    assert "portfolios" in restored_schema
    assert "positions" in restored_schema
    assert "orders" in restored_schema
    assert "ledger_events" in restored_schema

    restored_session_factory = sessionmaker(bind=restored_engine)
    with restored_session_factory() as r_session:
        r_inst = r_session.scalar(select(Instrument).where(Instrument.symbol == "RELIANCE"))
        assert r_inst is not None
        assert r_inst.isin == "INE002A01018"

        r_acct = r_session.scalar(select(Account).where(Account.account_number == "FP-BACKUP-001"))
        assert r_acct is not None
        assert r_acct.initial_scenario_capital == Decimal("30000.00")

        r_pos = r_session.scalar(select(Position).where(Position.portfolio_id == saved_port_id))
        assert r_pos is not None
        assert r_pos.quantity == 5

        r_ord = r_session.scalar(select(Order).where(Order.id == "ord_backup_test_01"))
        assert r_ord is not None
        assert r_ord.status == OrderStatus.FILLED.value

        r_evt = r_session.scalar(
            select(LedgerEvent).where(LedgerEvent.event_id == "evt_backup_test_01")
        )
        assert r_evt is not None
        assert r_evt.sequence_number == 1
        assert r_evt.payload == payload

    restored_engine.dispose()


def test_restore_tampered_backup_fails_checksum_verification(tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    backup_file = tmp_path / "backup.db"
    target_db = tmp_path / "target.db"

    # Create dummy database
    eng = create_engine(f"sqlite:///{source_db.as_posix()}")
    Base.metadata.create_all(eng)
    eng.dispose()

    valid_sha256 = backup_sqlite_database(source_db, backup_file)

    # Tamper with backup file bytes
    with backup_file.open("ab") as f:
        f.write(b"TAMPERED_MALICIOUS_BYTES")

    # Restoration with expected checksum must raise ValueError
    with pytest.raises(ValueError) as exc:
        restore_sqlite_database(backup_file, target_db, expected_sha256=valid_sha256)
    assert "mismatch" in str(exc.value).lower()
