from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from qmrsmithbot.workflows.action_ledger import ActionLedgerEntry
from qmrsmithbot.workflows.actions import (
    ActionEngine,
    ActionExecutionError,
    ActionFailureKind,
    ActionResult,
)
from qmrsmithbot.workflows.durable_action_executor import (
    ActionExecutionDeferred,
    DurableActionExecutor,
)
from qmrsmithbot.workflows.executor import ExecutionContext, ExecutionIdentity, WorkflowExecutor
from qmrsmithbot.workflows.schema import WorkflowDefinition


def make_entry(*, status: str = "pending", retryable: bool = False) -> ActionLedgerEntry:
    return ActionLedgerEntry(
        id=uuid4(),
        execution_id=uuid4(),
        tenant_id=uuid4(),
        project_id=uuid4(),
        node_id="send",
        action_type="action.message",
        idempotency_key="key",
        sequence=1,
        status=status,
        attempt=1,
        retryable=retryable,
        result_metadata={},
        error=None,
        completed_at=None,
        lease_expires_at=(
            datetime.now(UTC) + timedelta(minutes=1) if status == "running" else None
        ),
    )


def make_context() -> ExecutionContext:
    return ExecutionContext(
        identity=ExecutionIdentity(
            tenant_id=str(uuid4()),
            project_id=str(uuid4()),
            update_id=42,
            workflow_version_id=str(uuid4()),
            workflow_version=1,
            trace_id=str(uuid4()),
        )
    )


@pytest.mark.asyncio
async def test_durable_executor_claims_executes_and_completes() -> None:
    ledger = AsyncMock()
    scheduler = AsyncMock()
    engine = AsyncMock(spec=ActionEngine)
    entry = make_entry()
    completed = make_entry(status="completed")
    ledger.get_or_create.return_value = entry
    ledger.claim.return_value = entry
    ledger.complete.return_value = completed
    engine.execute.return_value = ActionResult(
        "action.message", "telegram:message:42", 1, {"message_id": 42}
    )

    durable = DurableActionExecutor(object(), engine, execution_id=entry.execution_id)
    durable.ledger = ledger
    durable.retry_scheduler = scheduler

    result = await durable.execute(
        node=SimpleNamespace(id="send", type="action.message", config={}),
        context=make_context(),
        sequence=1,
    )

    engine.execute.assert_awaited_once()
    ledger.complete.assert_awaited_once()
    scheduler.schedule.assert_not_awaited()
    assert result.ledger_id == completed.id
    assert result.result.external_key == "telegram:message:42"


@pytest.mark.asyncio
async def test_completed_ledger_entry_is_returned_without_reexecution() -> None:
    ledger = AsyncMock()
    engine = AsyncMock(spec=ActionEngine)
    entry = make_entry(status="completed")
    entry.result_metadata = {"external_key": "telegram:message:9", "message_id": 9}
    ledger.get_or_create.return_value = entry

    durable = DurableActionExecutor(object(), engine, execution_id=entry.execution_id)
    durable.ledger = ledger

    result = await durable.execute(
        node=SimpleNamespace(id="send", type="action.message", config={}),
        context=make_context(),
        sequence=1,
    )

    engine.execute.assert_not_awaited()
    ledger.claim.assert_not_awaited()
    assert result.result.external_key == "telegram:message:9"
    assert result.result.metadata == {"message_id": 9}


@pytest.mark.asyncio
async def test_retryable_failure_is_recorded_and_scheduled() -> None:
    ledger = AsyncMock()
    scheduler = AsyncMock()
    engine = AsyncMock(spec=ActionEngine)
    entry = make_entry()
    failed = make_entry(status="failed", retryable=True)
    ledger.get_or_create.return_value = entry
    ledger.claim.return_value = entry
    ledger.fail.return_value = failed
    engine.execute.side_effect = ActionExecutionError(
        "temporary failure", kind=ActionFailureKind.RETRYABLE
    )

    durable = DurableActionExecutor(object(), engine, execution_id=entry.execution_id)
    durable.ledger = ledger
    durable.retry_scheduler = scheduler

    with pytest.raises(ActionExecutionError):
        await durable.execute(
            node=SimpleNamespace(id="send", type="action.message", config={}),
            context=make_context(),
            sequence=1,
        )

    ledger.fail.assert_awaited_once()
    scheduler.schedule.assert_awaited_once_with(ledger_id=failed.id)


@pytest.mark.asyncio
async def test_workflow_executor_routes_action_nodes_to_durable_runner() -> None:
    runner = AsyncMock()
    runner.execute.return_value = SimpleNamespace(
        result=ActionResult("action.message", "telegram:message:1", 1, {"message_id": 1})
    )
    workflow = WorkflowDefinition(
        nodes=[
            {"id": "trigger", "type": "trigger.message"},
            {"id": "send", "type": "action.message"},
        ],
        edges=[{"source": "trigger", "target": "send"}],
    )

    context = await WorkflowExecutor(durable_action_runner=runner).run(workflow)

    runner.execute.assert_awaited_once()
    assert context.visited == ["trigger", "send"]
    assert context.values["message_id"] == 1


@pytest.mark.asyncio
async def test_durable_executor_defers_when_ledger_cannot_be_claimed() -> None:
    ledger = AsyncMock()
    engine = AsyncMock(spec=ActionEngine)
    entry = make_entry()
    ledger.get_or_create.return_value = entry
    ledger.claim.return_value = None

    durable = DurableActionExecutor(object(), engine, execution_id=entry.execution_id)
    durable.ledger = ledger

    with pytest.raises(ActionExecutionDeferred):
        await durable.execute(
            node=SimpleNamespace(id="send", type="action.message", config={}),
            context=make_context(),
            sequence=1,
        )
    engine.execute.assert_not_awaited()
