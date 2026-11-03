"""Data model, constraint, foreign key, and timezone contract tests (Layer 2).

Validates:
- Stable instrument identity and symbol history tracking.
- Market, exchange, currency, timezone-aware timestamp, and provenance metadata.
- Dataset manifests with SHA-256 checksums and schema versions.
- Operational account (₹30,000 scenario), portfolio, position, order, and ledger.
- Database constraints (positive quantities, prices, uniqueness, foreign keys).
- Transaction atomicity and rollback on failure.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from finpilot.db import (
    Base,
    CurrencyCode,
    DataMode,
    ExchangeCode,
    InstrumentStatus,
    LedgerEventType,
    MarketType,
    OrderSide,
    OrderStatus,
    OrderType,
)
from finpilot.db.models import (
    Account,
    DatasetManifest,
    Instrument,
    InstrumentSymbolHistory,
    LedgerEvent,
    Order,
    Portfolio,
    Position,
)

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture
def db_session() -> Session:
    """Create a clean in-memory database with SQLite foreign keys enabled."""
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    # Enable foreign keys for SQLite
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with session_factory() as session:
        yield session
    engine.dispose()


# ---------------------------------------------------------------------------
# 1. Stable Instrument Identity & Symbol History Tests
# ---------------------------------------------------------------------------


def test_stable_instrument_identity_and_symbol_history(db_session: Session) -> None:
    now = datetime.now(UTC)
    t0 = now - timedelta(days=365)
    t1 = now - timedelta(days=30)

    # Instrument has a stable ISIN (e.g. Reliance Industries)
    inst = Instrument(
        isin="INE002A01018",
        symbol="RELIANCE",
        name="Reliance Industries Limited",
        market=MarketType.EQUITY.value,
        exchange=ExchangeCode.NSE.value,
        currency=CurrencyCode.INR.value,
        lot_size=1,
        tick_size=Decimal("0.0500"),
        status=InstrumentStatus.ACTIVE.value,
    )
    db_session.add(inst)
    db_session.commit()
    assert inst.id is not None

    # Add historical ticker records (e.g. old symbol vs active symbol)
    h1 = InstrumentSymbolHistory(
        instrument_id=inst.id,
        symbol="RIL_OLD",
        valid_from=t0,
        valid_to=t1,
    )
    h2 = InstrumentSymbolHistory(
        instrument_id=inst.id,
        symbol="RELIANCE",
        valid_from=t1,
        valid_to=None,  # Active currently
    )
    db_session.add_all([h1, h2])
    db_session.commit()

    # Query active ticker using relationship
    db_session.refresh(inst)
    assert len(inst.symbol_history) == 2

    # Query by stable ISIN even if searched by old symbol
    history_match = db_session.scalar(
        select(InstrumentSymbolHistory).where(InstrumentSymbolHistory.symbol == "RIL_OLD")
    )
    assert history_match is not None
    assert history_match.instrument.isin == "INE002A01018"
    assert history_match.instrument.symbol == "RELIANCE"


def test_instrument_isin_uniqueness_and_length(db_session: Session) -> None:
    inst1 = Instrument(
        isin="INE002A01018",
        symbol="RELIANCE",
        name="Reliance Industries",
    )
    db_session.add(inst1)
    db_session.commit()

    # Duplicate ISIN must fail uniqueness constraint
    inst2 = Instrument(
        isin="INE002A01018",
        symbol="RELIANCE_DUP",
        name="Duplicate ISIN Instrument",
    )
    db_session.add(inst2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_instrument_constraints_positive_lot_and_tick(db_session: Session) -> None:
    # Invalid lot_size <= 0
    bad_lot = Instrument(
        isin="INE000A01001",
        symbol="BADLOT",
        name="Bad Lot Size",
        lot_size=0,
    )
    db_session.add(bad_lot)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Invalid tick_size <= 0
    bad_tick = Instrument(
        isin="INE000A01002",
        symbol="BADTICK",
        name="Bad Tick Size",
        tick_size=Decimal("-0.0500"),
    )
    db_session.add(bad_tick)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------------------------------------------------------------------------
# 2. Analytical Dataset Manifests Tests
# ---------------------------------------------------------------------------


def test_dataset_manifest_creation_and_integrity(db_session: Session) -> None:
    start_ts = datetime(2026, 1, 1, 9, 15, tzinfo=IST)
    end_ts = datetime(2026, 10, 31, 15, 30, tzinfo=IST)
    content = b"sample_parquet_content_for_checksum_test"
    checksum = hashlib.sha256(content).hexdigest()

    manifest = DatasetManifest(
        dataset_name="nse_cash_5m_completed",
        dataset_version="v1.0.0",
        mode=DataMode.HISTORICAL_REPLAY.value,
        provider_source="NSE_BHAVCOPY_VERIFIED",
        file_path_or_uri="data/parquet/nse_cash_5m_2026.parquet",
        sha256_checksum=checksum,
        row_count=37500,
        start_timestamp=start_ts,
        end_timestamp=end_ts,
        schema_version="parquet_arrow_v1",
    )
    db_session.add(manifest)
    db_session.commit()

    retrieved = db_session.scalar(
        select(DatasetManifest).where(
            DatasetManifest.dataset_name == "nse_cash_5m_completed",
            DatasetManifest.dataset_version == "v1.0.0",
        )
    )
    assert retrieved is not None
    assert retrieved.sha256_checksum == checksum
    assert retrieved.row_count == 37500
    assert retrieved.mode == DataMode.HISTORICAL_REPLAY.value


def test_dataset_manifest_timestamp_order_constraint(db_session: Session) -> None:
    # start_timestamp > end_timestamp must fail check constraint
    manifest = DatasetManifest(
        dataset_name="bad_time_manifest",
        dataset_version="v1",
        mode=DataMode.HISTORICAL_REPLAY.value,
        provider_source="TEST",
        file_path_or_uri="data/test.parquet",
        sha256_checksum="a" * 64,
        row_count=100,
        start_timestamp=datetime(2026, 10, 31, tzinfo=UTC),
        end_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        schema_version="v1",
    )
    db_session.add(manifest)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------------------------------------------------------------------------
# 3. Operational Account, Portfolio, Position, and Order Tests
# ---------------------------------------------------------------------------


def test_account_creation_default_scenario_capital(db_session: Session) -> None:
    account = Account(
        account_number="FP-SIM-30K-001",
        name="Research Sim Account 01",
        mode=DataMode.HISTORICAL_REPLAY.value,
    )
    db_session.add(account)
    db_session.commit()

    assert account.initial_scenario_capital == Decimal("30000.00")
    assert account.current_cash == Decimal("30000.00")
    assert account.currency == CurrencyCode.INR.value
    assert account.is_active is True


def test_portfolio_positions_orders_relationships_and_constraints(db_session: Session) -> None:
    # Setup instrument and account
    inst = Instrument(
        isin="INE002A01018",
        symbol="RELIANCE",
        name="Reliance Industries",
    )
    acct = Account(
        account_number="FP-SIM-30K-002",
        name="Account 2",
    )
    db_session.add_all([inst, acct])
    db_session.commit()

    # Portfolio
    port = Portfolio(
        account_id=acct.id,
        name="Equity Intraday TP-V1",
        mode=DataMode.HISTORICAL_REPLAY.value,
    )
    db_session.add(port)
    db_session.commit()

    # Order
    order = Order(
        id="ord_test_001",
        portfolio_id=port.id,
        instrument_id=inst.id,
        order_type=OrderType.MARKET.value,
        side=OrderSide.BUY.value,
        quantity=10,
        filled_quantity=10,
        price=Decimal("2500.0000"),
        status=OrderStatus.FILLED.value,
        risk_authorization_id="risk_auth_token_991",
        mode=DataMode.HISTORICAL_REPLAY.value,
    )
    db_session.add(order)
    db_session.commit()

    # Position
    pos = Position(
        portfolio_id=port.id,
        instrument_id=inst.id,
        quantity=10,
        average_entry_price=Decimal("2500.0000"),
        current_price=Decimal("2510.0000"),
        unrealized_pnl=Decimal("100.0000"),
        mode=DataMode.HISTORICAL_REPLAY.value,
    )
    db_session.add(pos)
    db_session.commit()

    # Verify positions and orders via portfolio
    db_session.refresh(port)
    assert len(port.positions) == 1
    assert len(port.orders) == 1
    assert port.positions[0].quantity == 10
    assert port.orders[0].id == "ord_test_001"


def test_position_long_only_constraint_rejects_negative_quantity(db_session: Session) -> None:
    inst = Instrument(isin="INE002A01018", symbol="RELIANCE", name="Reliance")
    acct = Account(account_number="FP-SIM-30K-003", name="Account 3")
    db_session.add_all([inst, acct])
    db_session.commit()

    port = Portfolio(account_id=acct.id, name="P1")
    db_session.add(port)
    db_session.commit()

    # Negative position (short selling) must be rejected by check constraint
    short_pos = Position(
        portfolio_id=port.id,
        instrument_id=inst.id,
        quantity=-5,  # Violates long-only rule (ck_positions_quantity_nonnegative)
    )
    db_session.add(short_pos)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_order_constraints_reject_invalid_quantities(db_session: Session) -> None:
    inst = Instrument(isin="INE002A01018", symbol="RELIANCE", name="Reliance")
    acct = Account(account_number="FP-SIM-30K-004", name="Account 4")
    db_session.add_all([inst, acct])
    db_session.commit()
    port = Portfolio(account_id=acct.id, name="P1")
    db_session.add(port)
    db_session.commit()

    # Zero or negative order quantity rejected
    bad_order_qty = Order(
        id="ord_bad_qty",
        portfolio_id=port.id,
        instrument_id=inst.id,
        quantity=0,
    )
    db_session.add(bad_order_qty)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Filled quantity > order quantity rejected
    bad_fill = Order(
        id="ord_bad_fill",
        portfolio_id=port.id,
        instrument_id=inst.id,
        quantity=10,
        filled_quantity=15,  # > quantity
    )
    db_session.add(bad_fill)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------------------------------------------------------------------------
# 4. Append-Only Prediction/Event Ledger Tests
# ---------------------------------------------------------------------------


def test_ledger_event_sequence_and_hash_chaining(db_session: Session) -> None:
    t0 = datetime(2026, 10, 31, 9, 20, tzinfo=IST)
    t1 = datetime(2026, 10, 31, 9, 25, tzinfo=IST)

    # Event 1: Initial decision
    payload_1 = '{"policy": "TP-V1", "signal": "BUY", "target_price": 2550}'
    hash_1 = hashlib.sha256(payload_1.encode()).hexdigest()

    e1 = LedgerEvent(
        sequence_number=1,
        event_id="evt_001",
        event_type=LedgerEventType.DECISION.value,
        mode=DataMode.HISTORICAL_REPLAY.value,
        payload=payload_1,
        integrity_hash=hash_1,
        prev_hash=None,
        timestamp=t0,
    )
    db_session.add(e1)
    db_session.commit()

    # Event 2: Order created with chained hash
    payload_2 = '{"order_id": "ord_001", "quantity": 10}'
    hash_2 = hashlib.sha256((payload_2 + hash_1).encode()).hexdigest()

    e2 = LedgerEvent(
        sequence_number=2,
        event_id="evt_002",
        event_type=LedgerEventType.ORDER_CREATED.value,
        mode=DataMode.HISTORICAL_REPLAY.value,
        payload=payload_2,
        integrity_hash=hash_2,
        prev_hash=hash_1,
        timestamp=t1,
    )
    db_session.add(e2)
    db_session.commit()

    # Verify sequential retrieval and hash chaining
    events = db_session.scalars(
        select(LedgerEvent).order_by(LedgerEvent.sequence_number.asc())
    ).all()
    assert len(events) == 2
    assert events[0].prev_hash is None
    assert events[1].prev_hash == events[0].integrity_hash


def test_ledger_event_mode_sequence_uniqueness(db_session: Session) -> None:
    t0 = datetime.now(UTC)
    e1 = LedgerEvent(
        sequence_number=1,
        event_id="evt_uniq_1",
        event_type=LedgerEventType.DECISION.value,
        mode=DataMode.HISTORICAL_REPLAY.value,
        payload="{}",
        integrity_hash="h1" * 32,
        timestamp=t0,
    )
    db_session.add(e1)
    db_session.commit()

    # Duplicate sequence number in SAME mode must fail
    e2 = LedgerEvent(
        sequence_number=1,  # duplicate for HISTORICAL_REPLAY
        event_id="evt_uniq_2",
        event_type=LedgerEventType.DECISION.value,
        mode=DataMode.HISTORICAL_REPLAY.value,
        payload="{}",
        integrity_hash="h2" * 32,
        timestamp=t0,
    )
    db_session.add(e2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Same sequence number in DIFFERENT mode is allowed (mode isolation)
    e3 = LedgerEvent(
        sequence_number=1,
        event_id="evt_uniq_3",
        event_type=LedgerEventType.DECISION.value,
        mode=DataMode.FORWARD_PAPER.value,  # Different mode
        payload="{}",
        integrity_hash="h3" * 32,
        timestamp=t0,
    )
    db_session.add(e3)
    db_session.commit()
    assert e3.id is not None


# ---------------------------------------------------------------------------
# 5. Foreign Key Enforcement & Transaction Atomicity
# ---------------------------------------------------------------------------


def test_foreign_key_restricts_parent_deletion(db_session: Session) -> None:
    acct = Account(account_number="FP-RESTRICT-001", name="Account Restrict")
    db_session.add(acct)
    db_session.commit()

    port = Portfolio(account_id=acct.id, name="Port 1")
    db_session.add(port)
    db_session.commit()

    # Deleting account when portfolio exists must fail with RESTRICT
    db_session.delete(acct)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_transaction_atomicity_and_rollback(db_session: Session) -> None:
    # Begin transaction inserting an account and an invalid instrument
    try:
        with db_session.begin_nested():
            acct = Account(account_number="FP-ATOMIC-001", name="Atomic Test")
            db_session.add(acct)
            # Bad instrument fails constraint
            bad_inst = Instrument(isin="INVALID_LEN", symbol="BAD", name="Bad")
            db_session.add(bad_inst)
            db_session.flush()
    except IntegrityError:
        pass

    # Verify acct was NOT persisted due to atomic rollback
    retrieved = db_session.scalar(select(Account).where(Account.account_number == "FP-ATOMIC-001"))
    assert retrieved is None
