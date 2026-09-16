"""Add durable action execution leases.

Revision ID: 20260916_04
Revises: 20260916_03
Create Date: 2026-09-16
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | None = "20260916_04"
down_revision: str | None = "20260916_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "action_ledger",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_action_ledger_lease_expires_at", "action_ledger", ["lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_action_ledger_lease_expires_at", table_name="action_ledger")
    op.drop_column("action_ledger", "lease_expires_at")
