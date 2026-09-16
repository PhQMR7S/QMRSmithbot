from __future__ import annotations

from uuid import uuid4

from qmrsmithbot.db.workflow_runtime_models import ActionLedgerRecord
from qmrsmithbot.workflows.action_ledger import ActionLedgerService


def test_action_ledger_table_constraints():
    constraints = {constraint.name for constraint in ActionLedgerRecord.__table__.constraints}
    assert "uq_action_ledger_execution_node_key" in constraints
    assert "ck_action_ledger_attempt_positive" in constraints
    assert "ck_action_ledger_status" in constraints


def test_action_ledger_schema_includes_retry_state():
    columns = ActionLedgerRecord.__table__.c
    assert columns.retryable.nullable is False
    assert columns.retryable.default is not None
    assert columns.available_at.nullable is True


def test_action_ledger_entry_mapping_preserves_state():
    execution_id = uuid4()
    tenant_id = uuid4()
    project_id = uuid4()
    record = ActionLedgerRecord(
        execution_id=execution_id,
        tenant_id=tenant_id,
        project_id=project_id,
        node_id="send",
        action_type="action.message",
        idempotency_key="key-1",
        status="completed",
        attempt=2,
        retryable=False,
        result_metadata={"message_id": 42},
    )
    record.id = uuid4()
    entry = ActionLedgerService._to_entry(record)
    assert entry.id == record.id
    assert entry.execution_id == execution_id
    assert entry.tenant_id == tenant_id
    assert entry.project_id == project_id
    assert entry.idempotency_key == "key-1"
    assert entry.status == "completed"
    assert entry.attempt == 2
    assert entry.retryable is False
    assert entry.result_metadata == {"message_id": 42}
    assert entry.completed_at == record.completed_at


def test_action_ledger_entry_mapping_copies_metadata():
    metadata = {"message_id": 42}
    record = ActionLedgerRecord(
        execution_id=uuid4(),
        tenant_id=uuid4(),
        project_id=uuid4(),
        node_id="send",
        action_type="action.message",
        idempotency_key="key-2",
        retryable=False,
        result_metadata=metadata,
    )
    record.id = uuid4()
    entry = ActionLedgerService._to_entry(record)
    entry.result_metadata["message_id"] = 99
    assert record.result_metadata == metadata
