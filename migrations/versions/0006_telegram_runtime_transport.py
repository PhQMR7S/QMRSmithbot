"""Add Telegram webhook state and durable update inbox.

Revision ID: 0006_telegram_runtime_transport
Revises: 0005_telegram_bot_credentials
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_telegram_runtime_transport"
down_revision = "0005_telegram_bot_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_webhook_states",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("webhook_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="inactive"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["bot_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
        sa.CheckConstraint(
            "status IN ('inactive', 'active', 'error')",
            name="ck_telegram_webhook_states_status",
        ),
    )
    op.create_table(
        "telegram_update_inbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_bot_id", sa.BigInteger(), nullable=False),
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["bot_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "update_id", name="uq_telegram_update_project_update"),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed')",
            name="ck_telegram_update_inbox_status",
        ),
    )
    op.create_index("ix_telegram_update_inbox_project_id", "telegram_update_inbox", ["project_id"])
    op.create_index("ix_telegram_update_inbox_telegram_bot_id", "telegram_update_inbox", ["telegram_bot_id"])


def downgrade() -> None:
    op.drop_index("ix_telegram_update_inbox_telegram_bot_id", table_name="telegram_update_inbox")
    op.drop_index("ix_telegram_update_inbox_project_id", table_name="telegram_update_inbox")
    op.drop_table("telegram_update_inbox")
    op.drop_table("telegram_webhook_states")
