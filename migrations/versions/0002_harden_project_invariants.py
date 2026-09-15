"""Harden project and workflow invariants.

Revision ID: 0002_harden_project_invariants
Revises: 0001_initial_schema
Create Date: 2026-09-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_harden_project_invariants"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_bot_projects_status",
        "bot_projects",
        "status IN ('draft', 'running', 'stopped', 'error')",
    )
    op.create_check_constraint(
        "ck_bot_projects_version",
        "bot_projects",
        "active_version IS NULL OR active_version > 0",
    )
    op.create_check_constraint(
        "ck_workflow_versions_version_positive",
        "workflow_versions",
        "version > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_workflow_versions_version_positive", "workflow_versions", type_="check")
    op.drop_constraint("ck_bot_projects_version", "bot_projects", type_="check")
    op.drop_constraint("ck_bot_projects_status", "bot_projects", type_="check")
