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
