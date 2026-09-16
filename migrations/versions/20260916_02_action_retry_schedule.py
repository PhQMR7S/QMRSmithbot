"""Add durable action retry scheduling.

Revision ID: 20260916_02
Revises: 20260916_01
Create Date: 2026-09-16
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | None = "20260916_02"
down_revision: str | None = "20260916_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "action_ledger",
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "action_ledger",
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_action_ledger_available_at", "action_ledger", ["available_at"])
    op.alter_column("action_ledger", "retryable", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_action_ledger_available_at", table_name="action_ledger")
    op.drop_column("action_ledger", "available_at")
    op.drop_column("action_ledger", "retryable")
