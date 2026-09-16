"""Add workflow execution worker leases.

Revision ID: 20260916_07
Revises: 20260916_06
Create Date: 2026-09-16
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | None = "20260916_07"
down_revision: str | None = "20260916_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_executions",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workflow_executions",
        sa.Column("worker_id", sa.String(128), nullable=True),
    )
    op.create_index("ix_workflow_executions_lease_expires_at", "workflow_executions", ["lease_expires_at"])
    op.create_index("ix_workflow_executions_worker_id", "workflow_executions", ["worker_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_executions_worker_id", table_name="workflow_executions")
    op.drop_index("ix_workflow_executions_lease_expires_at", table_name="workflow_executions")
    op.drop_column("workflow_executions", "worker_id")
    op.drop_column("workflow_executions", "lease_expires_at")
