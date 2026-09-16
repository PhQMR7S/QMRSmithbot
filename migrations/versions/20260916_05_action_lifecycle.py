"""Add terminal cancellation and dead-letter action states.

Revision ID: 20260916_05
Revises: 20260916_04
Create Date: 2026-09-16
"""
from collections.abc import Sequence

from alembic import op

revision: str | None = "20260916_05"
down_revision: str | None = "20260916_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_action_ledger_status", "action_ledger", type_="check")
    op.create_check_constraint(
        "ck_action_ledger_status",
        "action_ledger",
        "status IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'dead_letter')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_action_ledger_status", "action_ledger", type_="check")
    op.create_check_constraint(
        "ck_action_ledger_status",
        "action_ledger",
        "status IN ('pending', 'running', 'completed', 'failed')",
    )
