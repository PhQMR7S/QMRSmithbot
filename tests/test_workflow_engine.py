import asyncio

import pytest

from qmrsmithbot.workflows.executor import (
    ExecutionContext,
    WorkflowExecutionError,
    WorkflowExecutor,
)
from qmrsmithbot.workflows.schema import WorkflowDefinition, WorkflowNode


async def test_workflow_executes_from_trigger() -> None:
    workflow = WorkflowDefinition.model_validate(
        {
            "nodes": [
                {"id": "start", "type": "trigger.command"},
                {"id": "reply", "type": "action.message"},
            ],
            "edges": [{"source": "start", "target": "reply"}],
        }
    )
    seen: list[str] = []

    async def handle(node: WorkflowNode, context: ExecutionContext) -> None:
        seen.append(node.id)

    await WorkflowExecutor({"action.message": handle}).run(workflow, ExecutionContext())
    assert seen == ["reply"]


def test_unknown_edge_is_rejected() -> None:
    with pytest.raises(ValueError, match="existing nodes"):
        WorkflowDefinition.model_validate(
            {
                "nodes": [{"id": "start", "type": "trigger.command"}],
                "edges": [{"source": "start", "target": "missing"}],
            }
        )


def test_empty_workflow_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 1 item"):
        WorkflowDefinition.model_validate({"nodes": []})


def test_workflow_without_trigger_is_rejected() -> None:
    with pytest.raises(ValueError, match="trigger node"):
        WorkflowDefinition.model_validate(
            {"nodes": [{"id": "reply", "type": "action.message"}]}
        )


def test_duplicate_edges_are_rejected() -> None:
    with pytest.raises(ValueError, match="edges must be unique"):
        WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {"id": "start", "type": "trigger.command"},
                    {"id": "reply", "type": "action.message"},
                ],
                "edges": [
                    {"source": "start", "target": "reply"},
                    {"source": "start", "target": "reply"},
                ],
            }
        )


async def test_workflow_step_limit_stops_cycles() -> None:
    workflow = WorkflowDefinition.model_validate(
        {
            "nodes": [
                {"id": "start", "type": "trigger.command"},
                {"id": "loop", "type": "action.message"},
            ],
            "edges": [
                {"source": "start", "target": "loop"},
                {"source": "loop", "target": "start"},
            ],
        }
    )

    async def handle(node: WorkflowNode, context: ExecutionContext) -> None:
        context.values["runs"] = context.values.get("runs", 0) + 1

    context = await WorkflowExecutor({"action.message": handle}, max_steps=10).run(
        workflow, ExecutionContext()
    )
    assert context.values["runs"] == 1


async def test_missing_action_handler_is_rejected() -> None:
    workflow = WorkflowDefinition.model_validate(
        {
            "nodes": [
                {"id": "start", "type": "trigger.command"},
                {"id": "reply", "type": "action.message"},
            ],
            "edges": [{"source": "start", "target": "reply"}],
        }
    )

    with pytest.raises(WorkflowExecutionError, match="no handler registered"):
        await WorkflowExecutor().run(workflow, ExecutionContext())


async def test_execution_limit_is_enforced_for_many_distinct_nodes() -> None:
    nodes = [{"id": "start", "type": "trigger.command"}]
    edges = []
    for index in range(1, 5):
        nodes.append({"id": f"node-{index}", "type": "action.message"})
        edges.append(
            {
                "source": f"node-{index - 1}" if index > 1 else "start",
                "target": f"node-{index}",
            }
        )

    workflow = WorkflowDefinition.model_validate({"nodes": nodes, "edges": edges})

    async def handle(node: WorkflowNode, context: ExecutionContext) -> None:
        return None

    with pytest.raises(WorkflowExecutionError, match="step limit"):
        await WorkflowExecutor({"action.message": handle}, max_steps=3).run(
            workflow, ExecutionContext()
        )


def test_executor_rejects_invalid_step_limit() -> None:
    with pytest.raises(ValueError, match="max_steps"):
        WorkflowExecutor(max_steps=0)


def test_executor_rejects_invalid_resource_limits() -> None:
    with pytest.raises(ValueError, match="max_values"):
        WorkflowExecutor(max_values=0)
    with pytest.raises(ValueError, match="max_value_bytes"):
        WorkflowExecutor(max_value_bytes=1023)
    with pytest.raises(ValueError, match="handler_timeout_seconds"):
        WorkflowExecutor(handler_timeout_seconds=0)
    with pytest.raises(ValueError, match="execution_timeout_seconds"):
        WorkflowExecutor(execution_timeout_seconds=0)


async def test_value_count_budget_is_enforced() -> None:
    workflow = WorkflowDefinition.model_validate(
        {"nodes": [{"id": "start", "type": "trigger.command"}]}
    )

    async def handle(node: WorkflowNode, context: ExecutionContext) -> None:
        context.values.update({"a": 1, "b": 2})

    with pytest.raises(WorkflowExecutionError, match="value count limit"):
        await WorkflowExecutor({"trigger.command": handle}, max_values=1).run(workflow)


async def test_value_size_budget_is_enforced() -> None:
    workflow = WorkflowDefinition.model_validate(
        {"nodes": [{"id": "start", "type": "trigger.command"}]}
    )

    async def handle(node: WorkflowNode, context: ExecutionContext) -> None:
        context.values["payload"] = "x" * 2048

    with pytest.raises(WorkflowExecutionError, match="value size limit"):
        await WorkflowExecutor({"trigger.command": handle}, max_value_bytes=1024).run(
            workflow,
            ExecutionContext(),
        )


async def test_handler_timeout_is_enforced() -> None:
    workflow = WorkflowDefinition.model_validate(
        {
            "nodes": [
                {"id": "start", "type": "trigger.command"},
                {"id": "slow", "type": "action.message"},
            ],
            "edges": [{"source": "start", "target": "slow"}],
        }
    )

    async def handle(node: WorkflowNode, context: ExecutionContext) -> None:
        await asyncio.sleep(0.05)

    with pytest.raises(WorkflowExecutionError, match="handler timed out"):
        await WorkflowExecutor(
            {"action.message": handle}, handler_timeout_seconds=0.001
        ).run(workflow)
