"""Add durable action ordering.

Revision ID: 20260916_03
Revises: 20260916_02
Create Date: 2026-09-16
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | None = "20260916_03"
down_revision: str | None = "20260916_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "action_ledger",
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_action_ledger_sequence_positive",
        "action_ledger",
        "sequence >= 1",
    )
    op.create_index(
        "ix_action_ledger_execution_sequence",
        "action_ledger",
        ["execution_id", "sequence"],
    )
    op.alter_column("action_ledger", "sequence", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_action_ledger_execution_sequence", table_name="action_ledger")
    op.drop_constraint(
        "ck_action_ledger_sequence_positive",
        "action_ledger",
        type_="check",
    )
    op.drop_column("action_ledger", "sequence")
