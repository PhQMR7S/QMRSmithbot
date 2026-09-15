"""Add durable Telegram worker lease state.

Revision ID: 0007_telegram_runtime_worker_leases
Revises: 0006_telegram_runtime_transport
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_telegram_runtime_worker_leases"
down_revision = "0006_telegram_runtime_transport"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "telegram_update_inbox",
        sa.Column("claimed_by", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "telegram_update_inbox",
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_telegram_update_inbox_claimed_by",
        "telegram_update_inbox",
        ["claimed_by"],
    )
    op.create_index(
        "ix_telegram_update_inbox_lease_until",
        "telegram_update_inbox",
        ["lease_until"],
    )
    op.create_check_constraint(
        "ck_telegram_update_inbox_attempts_nonnegative",
        "telegram_update_inbox",
        "attempts >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_telegram_update_inbox_attempts_nonnegative",
        "telegram_update_inbox",
        type_="check",
    )
    op.drop_index("ix_telegram_update_inbox_lease_until", table_name="telegram_update_inbox")
    op.drop_index("ix_telegram_update_inbox_claimed_by", table_name="telegram_update_inbox")
    op.drop_column("telegram_update_inbox", "lease_until")
    op.drop_column("telegram_update_inbox", "claimed_by")
