"""Add production identity and tenant administration schema.

Revision ID: 0004_production_identity_tenant_admin
Revises: 0003_identity_tenant_security
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_production_identity_tenant_admin"
down_revision = "0003_identity_tenant_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("identities", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column(
        "identities",
        sa.Column("email_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index("ix_identities_email", "identities", ["email"], unique=False)

    op.create_table(
        "tenant_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invited_by_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "role IN ('admin', 'editor', 'viewer')", name="ck_tenant_invitations_role"
        ),
    )
    op.create_index("ix_tenant_invitations_tenant_id", "tenant_invitations", ["tenant_id"])
    op.create_index("ix_tenant_invitations_email", "tenant_invitations", ["email"])
    op.create_index(
        "uq_active_tenant_invitation",
        "tenant_invitations",
        ["tenant_id", "email"],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )

    op.create_table(
        "oidc_login_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("state_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("code_verifier_ciphertext", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column(
            "user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_oidc_login_states_expires_at", "oidc_login_states", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_oidc_login_states_expires_at", table_name="oidc_login_states")
    op.drop_table("oidc_login_states")
    op.drop_index("uq_active_tenant_invitation", table_name="tenant_invitations")
    op.drop_index("ix_tenant_invitations_email", table_name="tenant_invitations")
    op.drop_index("ix_tenant_invitations_tenant_id", table_name="tenant_invitations")
    op.drop_table("tenant_invitations")
    op.drop_index("ix_identities_email", table_name="identities")
    op.drop_column("identities", "email_verified")
    op.drop_column("identities", "email")
