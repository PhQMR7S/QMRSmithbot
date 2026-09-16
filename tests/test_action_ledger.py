from __future__ import annotations

from uuid import uuid4

from qmrsmithbot.db.workflow_runtime_models import ActionLedgerRecord
from qmrsmithbot.workflows.action_ledger import ActionLedgerService


def test_action_ledger_table_has_idempotency_constraint():
    constraints = {constraint.name for constraint in ActionLedgerRecord.__table__.constraints}
    assert "uq_action_ledger_execution_node_key" in constraints


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
        attempt=1,
        result_metadata={"message_id": 42},
    )
    entry = ActionLedgerService._to_entry(record)
    assert entry.execution_id == execution_id
    assert entry.tenant_id == tenant_id
    assert entry.project_id == project_id
    assert entry.idempotency_key == "key-1"
    assert entry.status == "completed"
    assert entry.result_metadata == {"message_id": 42}
