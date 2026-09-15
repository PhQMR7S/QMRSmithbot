from qmrsmithbot.db.models import (
    AuditEvent,
    BotProjectRecord,
    IdentityRecord,
    SessionRecord,
    TenantMembershipRecord,
    TenantRecord,
    WorkflowVersionRecord,
)


def test_database_schema_contains_expected_tables() -> None:
    expected = {
        "users",
        "identities",
        "sessions",
        "tenants",
        "tenant_memberships",
        "bot_projects",
        "workflow_versions",
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
    foreign_keys = {fk.target_fullname for fk in BotProjectRecord.__table__.c.tenant_id.foreign_keys}
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


def test_audit_event_preserves_project_actor_and_tenant_links() -> None:
    foreign_keys = {fk.target_fullname for fk in AuditEvent.__table__.foreign_keys}
    assert "users.id" in foreign_keys
    assert "bot_projects.id" in foreign_keys
    assert "tenants.id" in foreign_keys


def test_tenant_model_has_unique_slug() -> None:
    assert TenantRecord.__table__.c.slug.unique is True
