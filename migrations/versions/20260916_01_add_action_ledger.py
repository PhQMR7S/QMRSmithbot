"""Add durable action ledger.

Revision ID: 20260916_01
Revises: 0007_telegram_runtime_worker_leases
Create Date: 2026-09-16
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260916_01"
down_revision: str | None = "0007_telegram_runtime_worker_leases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "action_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", sa.String(length=100), nullable=False),
        sa.Column("action_type", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("result_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("attempt >= 1", name="ck_action_ledger_attempt_positive"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_action_ledger_status",
        ),
        sa.ForeignKeyConstraint(["execution_id"], ["workflow_executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["bot_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "execution_id", "node_id", "idempotency_key", name="uq_action_ledger_execution_node_key"
        ),
    )
    op.create_index("ix_action_ledger_execution_id", "action_ledger", ["execution_id"])
    op.create_index("ix_action_ledger_project_id", "action_ledger", ["project_id"])
    op.create_index("ix_action_ledger_tenant_id", "action_ledger", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_action_ledger_tenant_id", table_name="action_ledger")
    op.drop_index("ix_action_ledger_project_id", table_name="action_ledger")
    op.drop_index("ix_action_ledger_execution_id", table_name="action_ledger")
    op.drop_table("action_ledger")
