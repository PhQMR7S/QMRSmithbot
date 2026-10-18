"""Button menus, direct Telegram file references and contact reply routing."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '20261017_05'
down_revision = '20261017_04'
branch_labels = None
depends_on = None


def upgrade():
    project = lambda: sa.Column('project_id', UUID(), sa.ForeignKey('bot_projects.id', ondelete='CASCADE'), primary_key=True)
    op.create_table('factory_buttons',
        sa.Column('id', UUID(), primary_key=True),
        sa.Column('project_id', UUID(), sa.ForeignKey('bot_projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('parent_id', UUID(), sa.ForeignKey('factory_buttons.id', ondelete='CASCADE')),
        sa.Column('draft', JSONB(), nullable=False), sa.Column('published', JSONB()),
        sa.Column('deleted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_factory_buttons_project_id', 'factory_buttons', ['project_id'])
    op.create_index('ix_factory_buttons_parent_id', 'factory_buttons', ['parent_id'])
    op.create_table('bot_owner_states', project(), sa.Column('data', JSONB(), nullable=False))
    op.create_table('contact_deliveries', project(), sa.Column('owner_message_id', sa.BigInteger(), primary_key=True),
                    sa.Column('visitor_id', sa.BigInteger(), nullable=False))
    op.create_table('contact_blocks', project(), sa.Column('visitor_id', sa.BigInteger(), primary_key=True),
                    sa.Column('blocked', sa.Boolean(), nullable=False))


def downgrade():
    for table in ('contact_blocks', 'contact_deliveries', 'bot_owner_states', 'factory_buttons'):
        op.drop_table(table)
