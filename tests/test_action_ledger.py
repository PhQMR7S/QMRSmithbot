from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
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


def test_action_ledger_schema_includes_retry_ordering_and_lease_state():
    columns = ActionLedgerRecord.__table__.c
    assert columns.retryable.nullable is False
    assert columns.retryable.default is not None
    assert columns.available_at.nullable is True
    assert columns.sequence.nullable is False
    assert columns.sequence.default is not None
    assert columns.lease_expires_at.nullable is True


def test_action_ledger_entry_mapping_preserves_lease_state():
    execution_id = uuid4()
    tenant_id = uuid4()
    project_id = uuid4()
    lease_expires_at = datetime.now(UTC) + timedelta(seconds=60)
    record = ActionLedgerRecord(
        execution_id=execution_id,
        tenant_id=tenant_id,
        project_id=project_id,
        node_id="send",
        action_type="action.message",
        idempotency_key="key-1",
        sequence=3,
        status="running",
        attempt=2,
        retryable=False,
        lease_expires_at=lease_expires_at,
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
    assert entry.status == "running"
    assert entry.attempt == 2
    assert entry.retryable is False
    assert entry.result_metadata == {"message_id": 42}
    assert entry.lease_expires_at == lease_expires_at


def test_action_ledger_ordering_claim_query_contains_predecessor_guard() -> None:
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    service = ActionLedgerService(session)

    asyncio.run(service.claim(ledger_id=uuid4()))
    statement = session.scalar.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "EXISTS" in sql.upper()
    assert "sequence <" in sql
    assert "status !=" in sql


def test_action_ledger_lease_recovery_statement_is_expiry_bound() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=type("Result", (), {"rowcount": 2})())
    service = ActionLedgerService(session, lease_seconds=30)
    now = datetime.now(UTC)

    assert asyncio.run(service.recover_expired_leases(now=now)) == 2
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "lease_expires_at" in sql
    assert "status" in sql
    values = statement.compile().params
    assert "action execution lease expired" in values.values()


def test_action_ledger_service_rejects_nonpositive_lease() -> None:
    session = AsyncMock()
    for value in (0, -1):
        try:
            ActionLedgerService(session, lease_seconds=value)
        except ValueError:
            pass
        else:
            raise AssertionError("non-positive lease must be rejected")
