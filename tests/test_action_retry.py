from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from qmrsmithbot.db.workflow_runtime_models import ActionLedgerRecord
from qmrsmithbot.workflows.action_retry import ActionRetryScheduler, RetrySchedule


def test_action_ledger_exposes_retry_scheduling_columns() -> None:
    columns = ActionLedgerRecord.__table__.c
    assert columns.retryable.type.python_type is bool
    assert columns.available_at.nullable is True
    assert columns.available_at.index is True


def test_delay_for_attempt_uses_capped_exponential_backoff() -> None:
    scheduler = ActionRetryScheduler(object(), base_delay_seconds=2, max_delay_seconds=10)  # type: ignore[arg-type]
    assert scheduler.delay_for_attempt(1) == 2
    assert scheduler.delay_for_attempt(2) == 4
    assert scheduler.delay_for_attempt(3) == 8
    assert scheduler.delay_for_attempt(4) == 10
    assert scheduler.delay_for_attempt(99) == 10


def test_retry_scheduler_rejects_invalid_delays() -> None:
    with pytest.raises(ValueError):
        ActionRetryScheduler(object(), base_delay_seconds=0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ActionRetryScheduler(object(), base_delay_seconds=5, max_delay_seconds=4)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ActionRetryScheduler(object()).delay_for_attempt(0)  # type: ignore[arg-type]


def test_retry_schedule_is_immutable_and_utc() -> None:
    now = datetime.now(UTC)
    schedule = RetrySchedule(
        ledger_id=uuid4(),
        attempt=2,
        available_at=now + timedelta(seconds=4),
        delay_seconds=4,
    )
    assert schedule.available_at.tzinfo is UTC
    with pytest.raises(AttributeError):
        schedule.attempt = 3  # type: ignore[misc]


def _ledger_record(*, retryable: bool, status: str = "failed") -> ActionLedgerRecord:
    record = ActionLedgerRecord(
        execution_id=uuid4(),
        tenant_id=uuid4(),
        project_id=uuid4(),
        node_id="send",
        action_type="action.message",
        idempotency_key=f"key-{uuid4()}",
        status=status,
        attempt=2,
        retryable=retryable,
        result_metadata={},
    )
    record.id = uuid4()
    return record


@pytest.mark.asyncio
async def test_schedule_schedules_retryable_failed_actions() -> None:
    record = _ledger_record(retryable=True)
    session = AsyncMock()
    session.scalar.return_value = record
    scheduler = ActionRetryScheduler(session, base_delay_seconds=2, max_delay_seconds=10)

    scheduled = await scheduler.schedule(ledger_id=record.id)

    assert scheduled is not None
    assert scheduled.ledger_id == record.id
    assert scheduled.attempt == 2
    assert scheduled.delay_seconds == 4
    assert scheduled.available_at > datetime.now(UTC)
    assert record.available_at == scheduled.available_at
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_schedule_skips_terminal_failed_actions() -> None:
    record = _ledger_record(retryable=False)
    session = AsyncMock()
    session.scalar.return_value = None
    scheduler = ActionRetryScheduler(session)

    scheduled = await scheduler.schedule(ledger_id=record.id)

    assert scheduled is None
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_claim_due_transitions_retryable_action_to_running() -> None:
    now = datetime.now(UTC)
    record = _ledger_record(retryable=True)
    record.available_at = now - timedelta(seconds=1)
    record.error = "temporary failure"

    session = AsyncMock()
    session.scalar.return_value = record
    scheduler = ActionRetryScheduler(session)

    claimed = await scheduler.claim_due(ledger_id=record.id, now=now)

    assert claimed is record
    assert record.status == "running"
    assert record.started_at == now
    assert record.available_at is None
    assert record.error is None
    session.flush.assert_awaited_once()
