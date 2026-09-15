from uuid import uuid4

import pytest

from qmrsmithbot.telegram.dispatcher import DispatchPlan, TelegramEvent, TriggerMatch
from qmrsmithbot.workflows.executor import (
    ExecutionContext,
    WorkflowExecutionError,
    WorkflowExecutor,
    WorkflowLimitExceeded,
)
from qmrsmithbot.workflows.schema import WorkflowDefinition


def _plan(definition: dict) -> DispatchPlan:
    workflow = WorkflowDefinition.model_validate(definition)
    trigger = next(node for node in workflow.nodes if node.type.startswith("trigger."))
    return DispatchPlan(
        project_id=uuid4(),
        tenant_id=uuid4(),
        update_id=1,
        workflow_version_id=uuid4(),
        workflow_version=1,
        event=TelegramEvent("command", 1, 1, 2, "/start", "start", None),
        triggers=(TriggerMatch(trigger.id, trigger.type),),
        definition=workflow,
    )


@pytest.mark.asyncio
async def test_executor_follows_reachable_nodes_and_conditions() -> None:
    calls: list[str] = []

    async def handler(node, context: ExecutionContext) -> None:
        calls.append(node.id)
        if node.id == "set":
            context.values["ready"] = True

    plan = _plan({
        "nodes": [
            {"id": "start", "type": "trigger.command"},
            {"id": "set", "type": "data.set"},
            {"id": "send", "type": "action.message"},
            {"id": "other", "type": "action.message"},
        ],
        "edges": [
            {"source": "start", "target": "set"},
            {"source": "set", "target": "send", "condition": "exists:ready"},
        ],
    })
    result = await WorkflowExecutor({"data.set": handler, "action.message": handler}).run(plan)
    assert calls == ["set", "send"]
    assert result.visited == ["start", "set", "send"]


@pytest.mark.asyncio
async def test_executor_rejects_missing_handler() -> None:
    plan = _plan({
        "nodes": [
            {"id": "start", "type": "trigger.command"},
            {"id": "send", "type": "action.message"},
        ],
        "edges": [{"source": "start", "target": "send"}],
    })
    with pytest.raises(WorkflowExecutionError):
        await WorkflowExecutor().run(plan)


@pytest.mark.asyncio
async def test_executor_enforces_step_budget() -> None:
    plan = _plan({
        "nodes": [
            {"id": "start", "type": "trigger.command"},
            {"id": "send", "type": "action.message"},
        ],
        "edges": [{"source": "start", "target": "send"}],
    })

    async def handler(node, context: ExecutionContext) -> None:
        return None

    with pytest.raises(WorkflowLimitExceeded):
        await WorkflowExecutor({"action.message": handler}, max_steps=1).run(plan)
