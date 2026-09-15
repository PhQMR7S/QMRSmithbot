"""Add encrypted Telegram bot credentials.

Revision ID: 0005_telegram_bot_credentials
Revises: 0004_production_identity_tenant_admin
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_telegram_bot_credentials"
down_revision = "0004_production_identity_tenant_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bot_credentials",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_ciphertext", sa.Text(), nullable=False),
        sa.Column("token_last4", sa.String(length=4), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("webhook_secret_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["bot_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
        sa.CheckConstraint("token_version > 0", name="ck_bot_credentials_token_version_positive"),
    )


def downgrade() -> None:
    op.drop_table("bot_credentials")
