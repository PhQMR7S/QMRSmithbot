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
