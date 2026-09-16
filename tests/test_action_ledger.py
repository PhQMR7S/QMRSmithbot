from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
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
    result = MagicMock()
    result.all.return_value = []
    session.scalars = AsyncMock(return_value=result)
    service = ActionLedgerService(session, lease_seconds=30)
    now = datetime.now(UTC)

    assert asyncio.run(service.recover_expired_leases(now=now)) == 0
    statement = session.scalars.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "lease_expires_at" in sql
    assert "status" in sql
    values = statement.compile().params
    assert now in values.values()


def test_action_ledger_service_rejects_nonpositive_lease() -> None:
    session = AsyncMock()
    for value in (0, -1):
        try:
            ActionLedgerService(session, lease_seconds=value)
        except ValueError:
            pass
        else:
            raise AssertionError("non-positive lease must be rejected")


def _entry(**overrides):
    values = {
        "id": uuid4(),
        "execution_id": uuid4(),
        "tenant_id": uuid4(),
        "project_id": uuid4(),
        "node_id": "send",
        "action_type": "action.message",
        "idempotency_key": "key",
        "sequence": 1,
        "status": "running",
        "attempt": 3,
        "retryable": True,
        "result_metadata": {},
        "error": None,
        "available_at": None,
        "lease_expires_at": datetime.now(UTC),
        "completed_at": None,
    }
    values.update(overrides)
    return MagicMock(**values)


def test_fail_moves_final_retry_to_dead_letter() -> None:
    session = AsyncMock()
    row = _entry()
    session.scalar = AsyncMock(return_value=row)
    service = ActionLedgerService(session)

    result = asyncio.run(
        service.fail(ledger_id=row.id, error="provider unavailable", retryable=True, max_attempts=3)
    )

    assert result.status == "dead_letter"
    assert result.retryable is False
    assert row.status == "dead_letter"
    assert row.attempt == 3
    assert row.available_at is None
    assert row.lease_expires_at is None


def test_cancel_only_targets_pending_or_failed_actions() -> None:
    session = AsyncMock()
    row = _entry(status="failed")
    session.scalar = AsyncMock(return_value=row)
    service = ActionLedgerService(session)

    result = asyncio.run(service.cancel(ledger_id=row.id, reason="user requested cancellation"))

    assert result is not None
    assert result.status == "cancelled"
    assert result.retryable is False
    assert row.error == "user requested cancellation"


def test_replay_requeues_dead_letter_without_resetting_attempt_history() -> None:
    session = AsyncMock()
    row = _entry(status="dead_letter", attempt=4, error="permanent failure")
    session.scalar = AsyncMock(return_value=row)
    service = ActionLedgerService(session)

    result = asyncio.run(service.replay(ledger_id=row.id))

    assert result is not None
    assert result.status == "pending"
    assert result.attempt == 4
    assert result.retryable is False
    assert row.error is None
    assert row.lease_expires_at is None
