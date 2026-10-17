"""Optional PostgreSQL authentication rate limits for serverless deployments."""
import sqlalchemy as sa
from alembic import op

revision = '20261017_02'
down_revision = '20261017_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('security_rate_limits',
                    sa.Column('key', sa.String(64), primary_key=True),
                    sa.Column('count', sa.Integer(), nullable=False),
                    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
                    sa.CheckConstraint('count > 0', name='ck_security_rate_limit_count'))
    op.create_index('ix_security_rate_limits_expiry', 'security_rate_limits', ['expires_at'])


def downgrade():
    op.drop_table('security_rate_limits')
