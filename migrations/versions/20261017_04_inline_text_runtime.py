"""Bounded text runtime and durable webhook reply cache."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '20261017_04'
down_revision = '20261017_03'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('telegram_inline_bots',
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('bot_projects.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('webhook_url', sa.Text(), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True)))
    op.create_table('telegram_inline_updates',
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('bot_projects.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('update_id', sa.BigInteger(), primary_key=True),
        sa.Column('response', JSONB()),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_telegram_inline_updates_received_at', 'telegram_inline_updates', ['received_at'])


def downgrade():
    op.drop_table('telegram_inline_updates')
    op.drop_table('telegram_inline_bots')
