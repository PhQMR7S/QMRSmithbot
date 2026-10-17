from qmrsmithbot.db.models import (
    AuditEvent,
    BotCredentialRecord,
    BotProjectRecord,
    IdentityRecord,
    OIDCLoginStateRecord,
    SessionRecord,
    TenantInvitationRecord,
    TenantMembershipRecord,
    TenantRecord,
    WorkflowVersionRecord,
)
from qmrsmithbot.db.telegram_runtime_models import (
    TelegramUpdateInboxRecord,
    TelegramWebhookStateRecord,
)
from qmrsmithbot.db.workflow_runtime_models import (
    ActionLedgerRecord,
    WorkflowExecutionRecord,
)


def test_database_schema_contains_expected_tables() -> None:
    expected = {
        "users",
        "security_rate_limits",
        "telegram_login_challenges",
        "factory_updates",
        "telegram_inline_bots",
        "telegram_inline_updates",
        "factory_conversations",
        "identities",
        "sessions",
        "tenants",
        "tenant_memberships",
        "tenant_invitations",
        "oidc_login_states",
        "bot_credentials",
        "bot_projects",
        "telegram_webhook_states",
        "telegram_update_inbox",
        "workflow_versions",
        "workflow_executions",
        "action_ledger",
        "audit_events",
    }
    assert expected == {table.name for table in BotProjectRecord.metadata.tables.values()}


def test_identity_is_unique_per_provider_and_subject() -> None:
    names = {constraint.name for constraint in IdentityRecord.__table__.constraints}
    assert "uq_identity_provider_subject" in names


def test_session_token_hash_is_unique() -> None:
    assert SessionRecord.__table__.c.token_hash.unique is True


def test_tenant_membership_has_role_invariant() -> None:
    names = {constraint.name for constraint in TenantMembershipRecord.__table__.constraints}
    assert "ck_tenant_memberships_role" in names


def test_project_is_tenant_scoped() -> None:
    assert BotProjectRecord.__table__.c.tenant_id.nullable is False
    foreign_keys = {
        fk.target_fullname for fk in BotProjectRecord.__table__.c.tenant_id.foreign_keys
    }
    assert "tenants.id" in foreign_keys


def test_workflow_version_has_project_version_uniqueness() -> None:
    constraints = WorkflowVersionRecord.__table__.constraints
    assert any(
        constraint.name == "uq_workflow_project_version"
        and {column.name for column in constraint.columns} == {"project_id", "version"}
        for constraint in constraints
    )


def test_project_status_and_version_invariants_are_database_constrained() -> None:
    names = {constraint.name for constraint in BotProjectRecord.__table__.constraints}
    assert "ck_bot_projects_status" in names
    assert "ck_bot_projects_version" in names


def test_workflow_version_number_is_positive() -> None:
    names = {constraint.name for constraint in WorkflowVersionRecord.__table__.constraints}
    assert "ck_workflow_versions_version_positive" in names


def test_workflow_execution_has_update_version_uniqueness() -> None:
    constraints = WorkflowExecutionRecord.__table__.constraints
    assert any(
        constraint.name == "uq_workflow_execution_update_version"
        and {column.name for column in constraint.columns}
        == {"project_id", "update_id", "workflow_version_id"}
        for constraint in constraints
    )


def test_audit_event_preserves_project_actor_and_tenant_links() -> None:
    foreign_keys = {fk.target_fullname for fk in AuditEvent.__table__.foreign_keys}
    assert "users.id" in foreign_keys
    assert "bot_projects.id" in foreign_keys
    assert "tenants.id" in foreign_keys


def test_tenant_model_has_unique_slug() -> None:
    assert TenantRecord.__table__.c.slug.unique is True


def test_invitation_token_hash_is_unique() -> None:
    assert TenantInvitationRecord.__table__.c.token_hash.unique is True


def test_oidc_state_has_single_use_fields() -> None:
    assert OIDCLoginStateRecord.__table__.c.state_hash.unique is True
    assert OIDCLoginStateRecord.__table__.c.used_at.nullable is True


def test_bot_credentials_are_project_scoped_and_versioned() -> None:
    assert BotCredentialRecord.__table__.c.project_id.primary_key is True
    assert BotCredentialRecord.__table__.c.token_ciphertext.nullable is False
    assert BotCredentialRecord.__table__.c.webhook_secret_hash.nullable is False
    assert any(
        constraint.name == "ck_bot_credentials_token_version_positive"
        for constraint in BotCredentialRecord.__table__.constraints
    )


def test_webhook_state_is_project_scoped() -> None:
    assert TelegramWebhookStateRecord.__table__.c.project_id.primary_key is True
    assert TelegramWebhookStateRecord.__table__.c.webhook_url.nullable is False


def test_update_inbox_has_idempotency_and_lease_invariants() -> None:
    names = {constraint.name for constraint in TelegramUpdateInboxRecord.__table__.constraints}
    assert "uq_telegram_update_project_update" in names
    assert "ck_telegram_update_inbox_attempts_nonnegative" in names
    assert TelegramUpdateInboxRecord.__table__.c.payload.nullable is False
    assert TelegramUpdateInboxRecord.__table__.c.claimed_by.nullable is True
    assert TelegramUpdateInboxRecord.__table__.c.lease_until.nullable is True


def test_action_ledger_is_execution_and_tenant_scoped() -> None:
    foreign_keys = {fk.target_fullname for fk in ActionLedgerRecord.__table__.foreign_keys}
    assert "workflow_executions.id" in foreign_keys
    assert "bot_projects.id" in foreign_keys
    assert "tenants.id" in foreign_keys
