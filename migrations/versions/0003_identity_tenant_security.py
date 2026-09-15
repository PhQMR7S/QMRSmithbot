"""Add identity, sessions, tenants, memberships, and tenant-scoped projects.

Revision ID: 0003_identity_tenant_security
Revises: 0002_harden_project_invariants
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_identity_tenant_security"
down_revision: str | None = "0002_harden_project_invariants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "subject", name="uq_identity_provider_subject"),
    )
    op.create_index("ix_identities_user_id", "identities", ["user_id"])

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_session_token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_tenant_slug"),
    )
    op.create_index("ix_tenants_created_by_user_id", "tenants", ["created_by_user_id"])

    op.create_table(
        "tenant_memberships",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'editor', 'viewer')",
            name="ck_tenant_memberships_role",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "user_id"),
    )
    op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"])

    op.add_column(
        "bot_projects",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_bot_projects_tenant_id", "bot_projects", ["tenant_id"])
    op.create_foreign_key(
        "fk_bot_projects_tenant_id",
        "bot_projects",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.execute(
        sa.text(
            "INSERT INTO tenants (id, name, slug, created_by_user_id) "
            "SELECT md5('qmrsmithbot:personal:' || id::text)::uuid, "
            "'Personal workspace', 'personal-' || id::text, id "
            "FROM users "
            "ON CONFLICT (slug) DO NOTHING"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
            "SELECT t.id, t.created_by_user_id, 'owner' "
            "FROM tenants AS t "
            "WHERE t.slug LIKE 'personal-%' "
            "ON CONFLICT (tenant_id, user_id) DO NOTHING"
        )
    )
    op.execute(
        sa.text(
            "UPDATE bot_projects AS p "
            "SET tenant_id = t.id "
            "FROM tenants AS t "
            "WHERE t.created_by_user_id = p.owner_id "
            "AND t.slug = 'personal-' || p.owner_id::text"
        )
    )
    op.alter_column("bot_projects", "tenant_id", nullable=False)

    op.add_column(
        "audit_events",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.create_foreign_key(
        "fk_audit_events_tenant_id",
        "audit_events",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        sa.text(
            "UPDATE audit_events AS a "
            "SET tenant_id = p.tenant_id "
            "FROM bot_projects AS p "
            "WHERE a.project_id = p.id"
        )
    )


def downgrade() -> None:
    op.drop_constraint("fk_audit_events_tenant_id", "audit_events", type_="foreignkey")
    op.drop_index("ix_audit_events_tenant_id", table_name="audit_events")
    op.drop_column("audit_events", "tenant_id")
    op.drop_constraint("fk_bot_projects_tenant_id", "bot_projects", type_="foreignkey")
    op.drop_index("ix_bot_projects_tenant_id", table_name="bot_projects")
    op.drop_column("bot_projects", "tenant_id")
    op.drop_index("ix_tenant_memberships_user_id", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")
    op.drop_index("ix_tenants_created_by_user_id", table_name="tenants")
    op.drop_table("tenants")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_identities_user_id", table_name="identities")
    op.drop_table("identities")
