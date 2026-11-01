"""Create operational persistence foundation schema (Layer 2).

Reversible migration adding:
- instruments and instrument_symbol_history
- dataset_manifests
- accounts, portfolios, positions, orders
- ledger_events

Revision ID: 0002_persistence_foundation
Revises: 0001_baseline
Create Date: 2026-11-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_persistence_foundation"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. instruments table
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("isin", sa.String(length=12), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("market", sa.String(length=20), server_default="EQUITY", nullable=False),
        sa.Column("exchange", sa.String(length=10), server_default="NSE", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column("lot_size", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "tick_size",
            sa.Numeric(precision=8, scale=4),
            server_default="0.0500",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), server_default="ACTIVE", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("isin", name="uq_instruments_isin"),
        sa.CheckConstraint("lot_size > 0", name="ck_instruments_lot_size_positive"),
        sa.CheckConstraint("tick_size > 0", name="ck_instruments_tick_size_positive"),
        sa.CheckConstraint("length(isin) = 12", name="ck_instruments_isin_length"),
    )
    op.create_index("ix_instruments_isin", "instruments", ["isin"])
    op.create_index("ix_instruments_symbol", "instruments", ["symbol"])

    # 2. instrument_symbol_history table
    op.create_table(
        "instrument_symbol_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "instrument_id", "symbol", "valid_from", name="uq_instrument_symbol_valid_from"
        ),
    )
    op.create_index(
        "ix_instrument_symbol_history_instrument_id",
        "instrument_symbol_history",
        ["instrument_id"],
    )
    op.create_index(
        "ix_instrument_symbol_history_symbol", "instrument_symbol_history", ["symbol"]
    )
    op.create_index(
        "ix_symbol_history_lookup", "instrument_symbol_history", ["symbol", "valid_to"]
    )

    # 3. dataset_manifests table
    op.create_table(
        "dataset_manifests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("dataset_name", sa.String(length=100), nullable=False),
        sa.Column("dataset_version", sa.String(length=50), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("provider_source", sa.String(length=100), nullable=False),
        sa.Column("file_path_or_uri", sa.String(length=500), nullable=False),
        sa.Column("sha256_checksum", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("start_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "dataset_name", "dataset_version", "mode", name="uq_dataset_manifest_identity"
        ),
        sa.CheckConstraint("row_count >= 0", name="ck_dataset_manifest_row_count_nonnegative"),
        sa.CheckConstraint("start_timestamp <= end_timestamp", name="ck_dataset_manifest_ts_order"),
    )
    op.create_index("ix_dataset_manifests_dataset_name", "dataset_manifests", ["dataset_name"])
    op.create_index("ix_dataset_manifests_mode", "dataset_manifests", ["mode"])

    # 4. accounts table
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("account_number", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column(
            "initial_scenario_capital",
            sa.Numeric(precision=12, scale=2),
            server_default="30000.00",
            nullable=False,
        ),
        sa.Column(
            "current_cash",
            sa.Numeric(precision=12, scale=2),
            server_default="30000.00",
            nullable=False,
        ),
        sa.Column(
            "mode", sa.String(length=20), server_default="HISTORICAL_REPLAY", nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("account_number", name="uq_accounts_number"),
        sa.CheckConstraint(
            "initial_scenario_capital > 0", name="ck_accounts_initial_capital_positive"
        ),
    )
    op.create_index("ix_accounts_account_number", "accounts", ["account_number"])

    # 5. portfolios table
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "mode", sa.String(length=20), server_default="HISTORICAL_REPLAY", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("account_id", "name", name="uq_portfolio_account_name"),
    )
    op.create_index("ix_portfolios_account_id", "portfolios", ["account_id"])

    # 6. positions table
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "portfolio_id",
            sa.Integer(),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("instruments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "average_entry_price",
            sa.Numeric(precision=12, scale=4),
            server_default="0.0000",
            nullable=False,
        ),
        sa.Column(
            "current_price",
            sa.Numeric(precision=12, scale=4),
            server_default="0.0000",
            nullable=False,
        ),
        sa.Column(
            "realized_pnl",
            sa.Numeric(precision=12, scale=4),
            server_default="0.0000",
            nullable=False,
        ),
        sa.Column(
            "unrealized_pnl",
            sa.Numeric(precision=12, scale=4),
            server_default="0.0000",
            nullable=False,
        ),
        sa.Column(
            "mode", sa.String(length=20), server_default="HISTORICAL_REPLAY", nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "portfolio_id", "instrument_id", "mode", name="uq_position_portfolio_instrument_mode"
        ),
        sa.CheckConstraint("quantity >= 0", name="ck_positions_quantity_nonnegative"),
        sa.CheckConstraint(
            "average_entry_price >= 0", name="ck_positions_avg_entry_price_nonnegative"
        ),
        sa.CheckConstraint("current_price >= 0", name="ck_positions_current_price_nonnegative"),
    )
    op.create_index("ix_positions_portfolio_id", "positions", ["portfolio_id"])
    op.create_index("ix_positions_instrument_id", "positions", ["instrument_id"])

    # 7. orders table
    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column(
            "portfolio_id",
            sa.Integer(),
            sa.ForeignKey("portfolios.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("instruments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("order_type", sa.String(length=20), server_default="MARKET", nullable=False),
        sa.Column("side", sa.String(length=10), server_default="BUY", nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("filled_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("risk_authorization_id", sa.String(length=100), nullable=True),
        sa.Column(
            "mode", sa.String(length=20), server_default="HISTORICAL_REPLAY", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name="ck_orders_quantity_positive"),
        sa.CheckConstraint("filled_quantity >= 0", name="ck_orders_filled_quantity_nonnegative"),
        sa.CheckConstraint("filled_quantity <= quantity", name="ck_orders_filled_lte_quantity"),
    )
    op.create_index("ix_orders_portfolio_id", "orders", ["portfolio_id"])
    op.create_index("ix_orders_instrument_id", "orders", ["instrument_id"])
    op.create_index("ix_orders_risk_authorization_id", "orders", ["risk_authorization_id"])
    op.create_index("ix_orders_portfolio_status", "orders", ["portfolio_id", "status"])

    # 8. ledger_events table
    op.create_table(
        "ledger_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "portfolio_id",
            sa.Integer(),
            sa.ForeignKey("portfolios.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("instruments.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("integrity_hash", sa.String(length=64), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("event_id", name="uq_ledger_events_event_id"),
        sa.UniqueConstraint("mode", "sequence_number", name="uq_ledger_events_mode_seq"),
    )
    op.create_index("ix_ledger_events_event_id", "ledger_events", ["event_id"])
    op.create_index("ix_ledger_events_account_id", "ledger_events", ["account_id"])
    op.create_index("ix_ledger_events_portfolio_id", "ledger_events", ["portfolio_id"])
    op.create_index("ix_ledger_events_instrument_id", "ledger_events", ["instrument_id"])
    op.create_index("ix_ledger_events_mode", "ledger_events", ["mode"])
    op.create_index("ix_ledger_events_timestamp", "ledger_events", ["timestamp"])
    op.create_index(
        "ix_ledger_events_mode_timestamp", "ledger_events", ["mode", "timestamp"]
    )


def downgrade() -> None:
    op.drop_table("ledger_events")
    op.drop_table("orders")
    op.drop_table("positions")
    op.drop_table("portfolios")
    op.drop_table("accounts")
    op.drop_table("dataset_manifests")
    op.drop_table("instrument_symbol_history")
    op.drop_table("instruments")
