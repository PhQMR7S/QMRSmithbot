"""Add durable workflow execution checkpoint state.

Revision ID: 20260916_06
Revises: 20260916_05
Create Date: 2026-09-16
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str | None = "20260916_06"
down_revision: str | None = "20260916_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_workflow_execution_status", "workflow_executions", type_="check")
    op.create_check_constraint(
        "ck_workflow_execution_status",
        "workflow_executions",
        "status IN ('running', 'completed', 'failed', 'cancelled')",
    )
    op.add_column(
        "workflow_executions",
        sa.Column("pending_nodes", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "workflow_executions",
        sa.Column("context_values", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "workflow_executions",
        sa.Column("checkpoint_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_workflow_execution_checkpoint_nonnegative",
        "workflow_executions",
        "checkpoint_version >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_workflow_execution_checkpoint_nonnegative", "workflow_executions", type_="check")
    op.drop_column("workflow_executions", "checkpoint_version")
    op.drop_column("workflow_executions", "context_values")
    op.drop_column("workflow_executions", "pending_nodes")
    op.drop_constraint("ck_workflow_execution_status", "workflow_executions", type_="check")
    op.create_check_constraint(
        "ck_workflow_execution_status",
        "workflow_executions",
        "status IN ('running', 'completed', 'failed')",
    )
