import asyncio

import pytest

from qmrsmithbot.workflows.action_engine import ActionEngine
from qmrsmithbot.workflows.actions import (
    ActionExecutionError,
    ActionFailureKind,
    ActionRegistry,
    ActionResult,
)
from qmrsmithbot.workflows.executor import ExecutionContext
from qmrsmithbot.workflows.schema import WorkflowNode


class Handler:
    async def execute(self, *, node, context, attempt):
        return ActionResult(node.type, f"{context.project_id}:{node.id}", attempt, {})


@pytest.mark.asyncio
async def test_registry_only_allows_explicit_action_handlers() -> None:
    registry = ActionRegistry({"action.message": Handler()})
    engine = ActionEngine(registry)
    result = await engine.execute(
        node=WorkflowNode(id="send", type="action.message"),
        context=ExecutionContext(),
    )
    assert result.action_type == "action.message"

    with pytest.raises(ActionExecutionError) as error:
        await engine.execute(
            node=WorkflowNode(id="http", type="action.http"), context=ExecutionContext()
        )
    assert error.value.kind is ActionFailureKind.NON_RETRYABLE


@pytest.mark.asyncio
async def test_action_engine_enforces_timeout() -> None:
    class SlowHandler:
        async def execute(self, *, node, context, attempt):
            await asyncio.sleep(0.05)
            return ActionResult(node.type, node.id, attempt, {})

    engine = ActionEngine(ActionRegistry({"action.message": SlowHandler()}), action_timeout_seconds=0.001)
    with pytest.raises(ActionExecutionError, match="timed out"):
        await engine.execute(
            node=WorkflowNode(id="send", type="action.message"), context=ExecutionContext()
        )


def test_registry_rejects_duplicate_and_invalid_names() -> None:
    registry = ActionRegistry()
    registry.register("action.message", Handler())
    with pytest.raises(ValueError):
        registry.register("action.message", Handler())
    with pytest.raises(ValueError):
        registry.register("http", Handler())
