from dataclasses import dataclass
from uuid import uuid4

import pytest

from qmrsmithbot.workflows.executor import (
    ExecutionContext,
    ExecutionIdentity,
    WorkflowExecutionError,
    WorkflowExecutor,
)
from qmrsmithbot.workflows.schema import WorkflowDefinition


@dataclass(frozen=True)
class Trigger:
    node_id: str


@dataclass(frozen=True)
class Event:
    chat_id: int | None


@dataclass(frozen=True)
class Plan:
    project_id: object
    tenant_id: object
    update_id: int
    workflow_version_id: object
    workflow_version: int
    event: Event
    triggers: tuple[Trigger, ...]
    definition: WorkflowDefinition


@pytest.mark.asyncio
async def test_dispatch_plan_initializes_execution_identity() -> None:
    tenant_id = uuid4()
    project_id = uuid4()
    version_id = uuid4()
    workflow = WorkflowDefinition.model_validate(
        {"nodes": [{"id": "start", "type": "trigger.command"}]}
    )
    plan = Plan(
        project_id=project_id,
        tenant_id=tenant_id,
        update_id=42,
        workflow_version_id=version_id,
        workflow_version=7,
        event=Event(chat_id=1234),
        triggers=(Trigger("start"),),
        definition=workflow,
    )

    context = await WorkflowExecutor().run(plan)

    assert context.identity is not None
    assert context.identity.tenant_id == str(tenant_id)
    assert context.identity.project_id == str(project_id)
    assert context.identity.update_id == 42
    assert context.identity.workflow_version_id == str(version_id)
    assert context.identity.workflow_version == 7
    assert context.identity.chat_id == 1234
    assert context.trace_id is not None


def test_execution_identity_is_immutable() -> None:
    identity = ExecutionIdentity("tenant", "project", 1, "version", 1, "trace")
    with pytest.raises(AttributeError):
        identity.tenant_id = "other"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_context_cannot_be_reused_for_a_different_dispatch_identity() -> None:
    workflow = WorkflowDefinition.model_validate(
        {"nodes": [{"id": "start", "type": "trigger.command"}]}
    )
    first = Plan("project-a", "tenant-a", 1, "version-a", 1, Event(None), (Trigger("start"),), workflow)
    second = Plan("project-b", "tenant-a", 1, "version-a", 1, Event(None), (Trigger("start"),), workflow)
    context = await WorkflowExecutor().run(first)

    with pytest.raises(WorkflowExecutionError, match="identity does not match"):
        await WorkflowExecutor().run(second, context)


def test_execution_deadline_reports_remaining_time() -> None:
    context = ExecutionContext(deadline_monotonic=0.0)
    assert context.remaining_seconds() == 0.0
