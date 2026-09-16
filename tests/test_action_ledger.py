from __future__ import annotations

from uuid import uuid4

from sqlalchemy.dialects import postgresql

from qmrsmithbot.db.workflow_runtime_models import ActionLedgerRecord
from qmrsmithbot.workflows.action_ledger import ActionLedgerService


def test_action_ledger_table_constraints():
    constraints = {constraint.name for constraint in ActionLedgerRecord.__table__.constraints}
    assert "uq_action_ledger_execution_node_key" in constraints
    assert "ck_action_ledger_attempt_positive" in constraints
    assert "ck_action_ledger_sequence_positive" in constraints
    assert "ck_action_ledger_status" in constraints


def test_action_ledger_schema_includes_retry_and_ordering_state():
    columns = ActionLedgerRecord.__table__.c
    assert columns.retryable.nullable is False
    assert columns.retryable.default is not None
    assert columns.available_at.nullable is True
    assert columns.sequence.nullable is False
    assert columns.sequence.default is not None


def test_action_ledger_entry_mapping_preserves_ordering_state():
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
        sequence=3,
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
    assert entry.sequence == 3
    assert entry.status == "completed"
    assert entry.attempt == 2
    assert entry.retryable is False
    assert entry.result_metadata == {"message_id": 42}
    assert entry.completed_at == record.completed_at


def test_action_ledger_ordering_claim_query_requires_completed_predecessors():
    # Compile the claim statement shape by exercising the public method construction
    # without executing against a database.
    from unittest.mock import AsyncMock

    session = AsyncMock()
    scheduler = ActionLedgerService(session)
    import asyncio

    session.scalar = AsyncMock(return_value=None)
    asyncio.run(scheduler.claim(ledger_id=uuid4()))
    statement = session.scalar.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    sql = str(compiled)
    assert "status != 'completed'" in sql
    assert 'sequence < action_ledger.sequence' in sql
