from qmrsmithbot.workflows.executor import ExecutionContext, WorkflowExecutor
from qmrsmithbot.workflows.schema import WorkflowDefinition


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

    async def handle(node, context) -> None:
        seen.append(node.id)

    await WorkflowExecutor({"action.message": handle}).run(workflow, ExecutionContext())
    assert seen == ["reply"]


def test_unknown_edge_is_rejected() -> None:
    try:
        WorkflowDefinition.model_validate(
            {
                "nodes": [{"id": "start", "type": "trigger.command"}],
                "edges": [{"source": "start", "target": "missing"}],
            }
        )
    except ValueError as exc:
        assert "existing nodes" in str(exc)
    else:
        raise AssertionError("invalid workflow was accepted")
