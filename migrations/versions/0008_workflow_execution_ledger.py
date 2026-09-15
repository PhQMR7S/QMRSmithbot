"""workflow execution ledger

Revision ID: 0008
Revises: 0007_telegram_runtime_worker_leases
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_workflow_execution_ledger"
down_revision = "0007_telegram_runtime_worker_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bot_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("workflow_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("visited_nodes", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_workflow_execution_attempts_nonnegative"),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_workflow_execution_status"),
        sa.UniqueConstraint("project_id", "update_id", "workflow_version_id", name="uq_workflow_execution_update_version"),
    )
    op.create_index("ix_workflow_executions_project_id", "workflow_executions", ["project_id"])
    op.create_index("ix_workflow_executions_tenant_id", "workflow_executions", ["tenant_id"])
    op.create_index("ix_workflow_executions_workflow_version_id", "workflow_executions", ["workflow_version_id"])
    op.create_index("ix_workflow_executions_trace_id", "workflow_executions", ["trace_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_executions_trace_id", table_name="workflow_executions")
    op.drop_index("ix_workflow_executions_workflow_version_id", table_name="workflow_executions")
    op.drop_index("ix_workflow_executions_tenant_id", table_name="workflow_executions")
    op.drop_index("ix_workflow_executions_project_id", table_name="workflow_executions")
    op.drop_table("workflow_executions")
