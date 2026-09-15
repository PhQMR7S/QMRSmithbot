from qmrsmithbot.db.models import AuditEvent, BotProjectRecord, WorkflowVersionRecord


def test_database_schema_contains_expected_tables() -> None:
    assert {"users", "bot_projects", "workflow_versions", "audit_events"} == {
        table.name for table in BotProjectRecord.metadata.tables.values()
    }


def test_workflow_version_has_project_version_uniqueness() -> None:
    constraints = WorkflowVersionRecord.__table__.constraints
    assert any(
        constraint.name == "uq_workflow_project_version"
        and {column.name for column in constraint.columns} == {"project_id", "version"}
        for constraint in constraints
    )


def test_project_status_and_version_invariants_are_database_constrained() -> None:
    constraints = BotProjectRecord.__table__.constraints
    names = {constraint.name for constraint in constraints}
    assert "ck_bot_projects_status" in names
    assert "ck_bot_projects_version" in names


def test_workflow_version_number_is_positive() -> None:
    names = {constraint.name for constraint in WorkflowVersionRecord.__table__.constraints}
    assert "ck_workflow_versions_version_positive" in names


def test_audit_event_preserves_project_and_actor_links() -> None:
    foreign_keys = {foreign_key.target_fullname for foreign_key in AuditEvent.__table__.foreign_keys}
    assert "users.id" in foreign_keys
    assert "bot_projects.id" in foreign_keys
