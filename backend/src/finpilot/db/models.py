"""SQLAlchemy ORM models for the operational database (Layer 2).

Implements:
- Stable instrument identity and symbol-history model.
- Market, exchange, currency, timezone-aware timestamp, and provenance metadata.
- Analytical dataset manifests, schema/version metadata, and checksums.
- Operational account, portfolio, position, order, and append-only ledger structures.
- Strict database constraints, indexes, and uniqueness rules.

Governed by ARCHITECTURE.md §5, PROJECT_SPEC.md §3, §10-11, and Layer 2 Gate.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import (
    CurrencyCode,
    DataMode,
    ExchangeCode,
    InstrumentStatus,
    MarketType,
    OrderSide,
    OrderStatus,
    OrderType,
)


class Instrument(Base):
    """Stable instrument identity model (SEC-06, Layer 2).

    The ISIN is globally unique and immutable across corporate rebranding or ticker changes.
    The ``symbol`` represents the current trading ticker. Historical symbol changes are tracked
    in ``InstrumentSymbolHistory``.
    """

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    isin: Mapped[str] = mapped_column(String(12), unique=True, index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    market: Mapped[str] = mapped_column(
        String(20), default=MarketType.EQUITY.value, nullable=False
    )
    exchange: Mapped[str] = mapped_column(
        String(10), default=ExchangeCode.NSE.value, nullable=False
    )
    currency: Mapped[str] = mapped_column(
        String(3), default=CurrencyCode.INR.value, nullable=False
    )
    lot_size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    tick_size: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), default=Decimal("0.0500"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default=InstrumentStatus.ACTIVE.value, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    symbol_history: Mapped[list[InstrumentSymbolHistory]] = relationship(
        "InstrumentSymbolHistory", back_populates="instrument", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("lot_size > 0", name="ck_instruments_lot_size_positive"),
        CheckConstraint("tick_size > 0", name="ck_instruments_tick_size_positive"),
        CheckConstraint("length(isin) = 12", name="ck_instruments_isin_length"),
    )


class InstrumentSymbolHistory(Base):
    """Tracks historical ticker symbol changes preserving stable instrument identity."""

    __tablename__ = "instrument_symbol_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    instrument: Mapped[Instrument] = relationship("Instrument", back_populates="symbol_history")

    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "symbol", "valid_from", name="uq_instrument_symbol_valid_from"
        ),
        Index("ix_symbol_history_lookup", "symbol", "valid_to"),
    )


class DatasetManifest(Base):
    """Manifests for analytical datasets (Parquet/Arrow files) with integrity checksums.

    Large historical analytical data lives in partitioned Parquet/Arrow files; this table
    tracks their schema version, time span, row counts, and cryptographic checksums.
    """

    __tablename__ = "dataset_manifests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(50), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    provider_source: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path_or_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    start_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "dataset_name", "dataset_version", "mode", name="uq_dataset_manifest_identity"
        ),
        CheckConstraint("row_count >= 0", name="ck_dataset_manifest_row_count_nonnegative"),
        CheckConstraint("start_timestamp <= end_timestamp", name="ck_dataset_manifest_ts_order"),
    )


class Account(Base):
    """Operational simulation account model.

    Default scenario capital is ₹30,000 per Layer 0 contract.
    No live money is handled in V1.
    """

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_number: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default=CurrencyCode.INR.value, nullable=False)
    initial_scenario_capital: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("30000.00"), nullable=False
    )
    current_cash: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("30000.00"), nullable=False
    )
    mode: Mapped[str] = mapped_column(
        String(20), default=DataMode.HISTORICAL_REPLAY.value, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    portfolios: Mapped[list[Portfolio]] = relationship("Portfolio", back_populates="account")

    __table_args__ = (
        CheckConstraint(
            "initial_scenario_capital > 0", name="ck_accounts_initial_capital_positive"
        ),
    )


class Portfolio(Base):
    """Operational portfolio grouping positions and orders for an account."""

    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(
        String(20), default=DataMode.HISTORICAL_REPLAY.value, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    account: Mapped[Account] = relationship("Account", back_populates="portfolios")
    positions: Mapped[list[Position]] = relationship("Position", back_populates="portfolio")
    orders: Mapped[list[Order]] = relationship("Order", back_populates="portfolio")

    __table_args__ = (
        UniqueConstraint("account_id", "name", name="uq_portfolio_account_name"),
    )


class Position(Base):
    """Operational position in an instrument.

    FinPilot V1 is long-only equity cash: quantity must be non-negative integer (no short selling).
    """

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_entry_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), default=Decimal("0.0000"), nullable=False
    )
    current_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), default=Decimal("0.0000"), nullable=False
    )
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), default=Decimal("0.0000"), nullable=False
    )
    unrealized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), default=Decimal("0.0000"), nullable=False
    )
    mode: Mapped[str] = mapped_column(
        String(20), default=DataMode.HISTORICAL_REPLAY.value, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    portfolio: Mapped[Portfolio] = relationship("Portfolio", back_populates="positions")
    instrument: Mapped[Instrument] = relationship("Instrument")

    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "instrument_id", "mode", name="uq_position_portfolio_instrument_mode"
        ),
        CheckConstraint("quantity >= 0", name="ck_positions_quantity_nonnegative"),
        CheckConstraint(
            "average_entry_price >= 0", name="ck_positions_avg_entry_price_nonnegative"
        ),
        CheckConstraint("current_price >= 0", name="ck_positions_current_price_nonnegative"),
    )


class Order(Base):
    """Operational simulated order record.

    Includes risk authorization reference (sole authority per Layer 0).
    """

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("portfolios.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    order_type: Mapped[str] = mapped_column(
        String(20), default=OrderType.MARKET.value, nullable=False
    )
    side: Mapped[str] = mapped_column(String(10), default=OrderSide.BUY.value, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=OrderStatus.PENDING.value, nullable=False
    )
    risk_authorization_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    mode: Mapped[str] = mapped_column(
        String(20), default=DataMode.HISTORICAL_REPLAY.value, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    portfolio: Mapped[Portfolio] = relationship("Portfolio", back_populates="orders")
    instrument: Mapped[Instrument] = relationship("Instrument")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_orders_quantity_positive"),
        CheckConstraint("filled_quantity >= 0", name="ck_orders_filled_quantity_nonnegative"),
        CheckConstraint("filled_quantity <= quantity", name="ck_orders_filled_lte_quantity"),
        Index("ix_orders_portfolio_status", "portfolio_id", "status"),
    )


class LedgerEvent(Base):
    """Append-only prediction and event ledger (ARCHITECTURE.md §5, Layer 0 §11).

    Maintains sequential integrity hashes for tamper detection.
    """

    __tablename__ = "ledger_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    portfolio_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("portfolios.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    mode: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded event payload
    integrity_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("mode", "sequence_number", name="uq_ledger_events_mode_seq"),
        Index("ix_ledger_events_mode_timestamp", "mode", "timestamp"),
    )
