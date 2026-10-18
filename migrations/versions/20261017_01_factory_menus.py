"""Persist factory update deduplication and menu conversations."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '20261017_01'
down_revision = '20260916_07'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('factory_updates',
                    sa.Column('bot_id', sa.BigInteger(), primary_key=True),
                    sa.Column('update_id', sa.BigInteger(), primary_key=True),
                    sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table('factory_conversations',
                    sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
                    sa.Column('step', sa.String(32), nullable=False),
                    sa.Column('data', postgresql.JSONB(), nullable=False))


def downgrade():
    op.drop_table('factory_conversations')
    op.drop_table('factory_updates')
