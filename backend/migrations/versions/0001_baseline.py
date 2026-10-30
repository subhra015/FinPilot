"""Baseline migration: schema metadata table only.

Layer 1 intentionally creates no business tables. This baseline exists to prove
the migration chain is reversible before real schema arrives in later layers.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schema_meta",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("schema_version", sa.String(length=50), nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("schema_meta")
