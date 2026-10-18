"""One-time browser-bound Telegram login challenges."""
import sqlalchemy as sa
from alembic import op

revision = '20261017_03'
down_revision = '20261017_02'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('telegram_login_challenges',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('browser_secret_hash', sa.String(64), nullable=False),
        sa.Column('code_hash', sa.String(64), nullable=False),
        sa.Column('bot_id', sa.BigInteger(), nullable=False),
        sa.Column('telegram_user_id', sa.BigInteger()),
        sa.Column('approved_user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE')),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint('attempts >= 0 AND attempts <= 5', name='ck_telegram_login_attempts'))
    op.create_index('ix_telegram_login_challenges_expires_at', 'telegram_login_challenges', ['expires_at'])


def downgrade():
    op.drop_table('telegram_login_challenges')
