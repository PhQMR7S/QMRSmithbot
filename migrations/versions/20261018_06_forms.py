"""Durable form sessions and completed submissions."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '20261018_06'
down_revision = '20261017_05'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('bot_form_sessions',
        sa.Column('project_id',UUID(),sa.ForeignKey('bot_projects.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('visitor_id',sa.BigInteger(),primary_key=True),
        sa.Column('data',JSONB(),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_bot_form_sessions_expires_at','bot_form_sessions',['expires_at'])
    op.create_table('bot_form_submissions',
        sa.Column('id',UUID(),primary_key=True),
        sa.Column('project_id',UUID(),sa.ForeignKey('bot_projects.id',ondelete='CASCADE'),nullable=False),
        sa.Column('visitor_id',sa.BigInteger(),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('data',JSONB(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_index('ix_bot_form_submissions_project_id','bot_form_submissions',['project_id'])
    op.create_index('ix_bot_form_submissions_created_at','bot_form_submissions',['created_at'])
    op.create_index('ix_bot_form_submissions_project_created','bot_form_submissions',['project_id','created_at','id'])


def downgrade():
    op.drop_table('bot_form_submissions')
    op.drop_table('bot_form_sessions')
