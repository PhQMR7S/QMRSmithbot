from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from qmrsmithbot.workflows.schema import WorkflowDefinition, WorkflowNode


@dataclass(frozen=True, slots=True)
class ExecutionIdentity:
    """Immutable identity binding one execution to its tenant and published version."""

    tenant_id: str
    project_id: str
    update_id: int
    workflow_version_id: str
    workflow_version: int
    trace_id: str
    chat_id: int | None = None


@dataclass(slots=True)
class ExecutionContext:
    """Mutable workflow state with immutable execution identity and bounded data."""

    identity: ExecutionIdentity | None = None
    event: Mapping[str, Any] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)
    visited: list[str] = field(default_factory=list)
    steps: int = 0
    started_monotonic: float = field(default_factory=time.monotonic)
    deadline_monotonic: float | None = None

    @property
    def trace_id(self) -> str | None:
        return self.identity.trace_id if self.identity else None

    @property
    def tenant_id(self) -> str | None:
        return self.identity.tenant_id if self.identity else None

    @property
    def project_id(self) -> str | None:
        return self.identity.project_id if self.identity else None

    @property
    def update_id(self) -> int | None:
        return self.identity.update_id if self.identity else None

    @property
    def workflow_version_id(self) -> str | None:
        return self.identity.workflow_version_id if self.identity else None

    @property
    def chat_id(self) -> int | None:
        return self.identity.chat_id if self.identity else None

    def remaining_seconds(self) -> float | None:
        if self.deadline_monotonic is None:
            return None
        return max(0.0, self.deadline_monotonic - time.monotonic())


class DispatchPlanLike(Protocol):
    """Transport-neutral shape consumed by the workflow executor."""

    definition: WorkflowDefinition
    triggers: tuple[Any, ...]
    project_id: Any
    tenant_id: Any
    update_id: int
    workflow_version_id: Any
    workflow_version: int
    event: Any


Handler = Callable[[WorkflowNode, ExecutionContext], Awaitable[None]]


class DurableActionRunner(Protocol):
    """Durable action boundary used by the workflow executor."""

    async def execute(
        self,
        *,
        node: WorkflowNode,
        context: ExecutionContext,
        sequence: int,
    ) -> Any: ...


class WorkflowExecutionError(RuntimeError):
    """Raised when a workflow cannot be executed safely."""


class WorkflowLimitExceeded(WorkflowExecutionError):
    """Raised when a workflow exceeds its execution budget."""


class WorkflowExecutor:
    """Bounded deterministic graph executor with optional durable action execution."""

    def __init__(
        self,
        handlers: dict[str, Handler] | None = None,
        *,
        max_steps: int = 1000,
        max_values: int = 256,
        max_value_bytes: int = 64 * 1024,
        handler_timeout_seconds: float | None = None,
        execution_timeout_seconds: float | None = None,
        durable_action_runner: DurableActionRunner | None = None,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be positive")
        if max_values < 1:
            raise ValueError("max_values must be positive")
        if max_value_bytes < 1024:
            raise ValueError("max_value_bytes must be at least 1024")
        if handler_timeout_seconds is not None and handler_timeout_seconds <= 0:
            raise ValueError("handler_timeout_seconds must be positive")
        if execution_timeout_seconds is not None and execution_timeout_seconds <= 0:
            raise ValueError("execution_timeout_seconds must be positive")
        self.handlers = handlers or {}
        self.max_steps = max_steps
        self.max_values = max_values
        self.max_value_bytes = max_value_bytes
        self.handler_timeout_seconds = handler_timeout_seconds
        self.execution_timeout_seconds = execution_timeout_seconds
        self.durable_action_runner = durable_action_runner

    async def run(
        self,
        workflow: WorkflowDefinition | DispatchPlanLike,
        context: ExecutionContext | None = None,
    ) -> ExecutionContext:
        execution = context or ExecutionContext()
        self._initialize_identity(workflow, execution)
        self._check_value_budget(execution.values)
        definition, matched = self._resolve_input(workflow)
        nodes = {node.id: node for node in definition.nodes}
        outgoing: dict[str, list[tuple[str, str | None]]] = {}
        for edge in definition.edges:
            outgoing.setdefault(edge.source, []).append((edge.target, edge.condition))

        queue = list(matched)
        action_sequence = sum(1 for node_id in execution.visited if nodes.get(node_id) and nodes[node_id].type.startswith("action."))
        while queue:
            self._check_execution_budget(execution)
            node_id = queue.pop(0)
            if node_id in execution.visited:
                continue
            node = nodes.get(node_id)
            if node is None:
                raise WorkflowExecutionError(f"unknown node: {node_id}")
            execution.steps += 1
            if execution.steps > self.max_steps:
                raise WorkflowLimitExceeded("workflow execution step limit exceeded")

            if node.type.startswith("action.") and self.durable_action_runner is not None:
                action_sequence += 1
                durable_result = await self.durable_action_runner.execute(
                    node=node,
                    context=execution,
                    sequence=action_sequence,
                )
                result = getattr(durable_result, "result", None)
                if result is not None:
                    execution.values.update(result.metadata)
            else:
                handler = self.handlers.get(node.type)
                if handler is None and not node.type.startswith("trigger."):
                    raise WorkflowExecutionError(f"no handler registered for node type: {node.type}")
                if handler is not None:
                    await self._run_handler(handler, node, execution)
            self._check_value_budget(execution.values)
            execution.visited.append(node_id)

            for target, condition in outgoing.get(node_id, []):
                if self._condition_matches(condition, execution.values):
                    queue.append(target)
        return execution

    async def _run_handler(self, handler: Handler, node: WorkflowNode, context: ExecutionContext) -> None:
        coroutine = handler(node, context)
        timeout = self.handler_timeout_seconds
        remaining = context.remaining_seconds()
        if remaining is not None:
            timeout = remaining if timeout is None else min(timeout, remaining)
        if timeout is None:
            await coroutine
            return
        if timeout <= 0:
            coroutine.close()
            raise WorkflowLimitExceeded("workflow execution time limit exceeded")
        try:
            await asyncio.wait_for(coroutine, timeout=timeout)
        except TimeoutError as exc:
            raise WorkflowLimitExceeded(
                f"workflow handler timed out for node: {node.id}"
            ) from exc

    def _check_execution_budget(self, context: ExecutionContext) -> None:
        remaining = context.remaining_seconds()
        if remaining is not None and remaining <= 0:
            raise WorkflowLimitExceeded("workflow execution time limit exceeded")
        if (
            self.execution_timeout_seconds is not None
            and time.monotonic() - context.started_monotonic >= self.execution_timeout_seconds
        ):
            raise WorkflowLimitExceeded("workflow execution time limit exceeded")

    @staticmethod
    def _initialize_identity(
        workflow: WorkflowDefinition | DispatchPlanLike,
        context: ExecutionContext,
    ) -> None:
        if not isinstance(workflow, WorkflowDefinition):
            if context.identity is None:
                context.identity = ExecutionIdentity(
                    tenant_id=str(workflow.tenant_id),
                    project_id=str(workflow.project_id),
                    update_id=workflow.update_id,
                    workflow_version_id=str(workflow.workflow_version_id),
                    workflow_version=workflow.workflow_version,
                    trace_id=str(uuid4()),
                    chat_id=getattr(workflow.event, "chat_id", None),
                )
            elif (
                context.identity.tenant_id != str(workflow.tenant_id)
                or context.identity.project_id != str(workflow.project_id)
                or context.identity.update_id != workflow.update_id
                or context.identity.workflow_version_id != str(workflow.workflow_version_id)
            ):
                raise WorkflowExecutionError("execution context identity does not match dispatch plan")

    def _check_value_budget(self, values: dict[str, Any]) -> None:
        if len(values) > self.max_values:
            raise WorkflowLimitExceeded("workflow value count limit exceeded")
        try:
            encoded = json.dumps(values, ensure_ascii=False, separators=(",", ":"), default=str)
        except (TypeError, ValueError, OverflowError) as exc:
            raise WorkflowExecutionError("workflow context contains unserializable values") from exc
        if len(encoded.encode("utf-8")) > self.max_value_bytes:
            raise WorkflowLimitExceeded("workflow value size limit exceeded")

    @staticmethod
    def _resolve_input(
        workflow: WorkflowDefinition | DispatchPlanLike,
    ) -> tuple[WorkflowDefinition, list[str]]:
        if isinstance(workflow, WorkflowDefinition):
            return workflow, [node.id for node in workflow.nodes if node.type.startswith("trigger.")]
        return workflow.definition, [trigger.node_id for trigger in workflow.triggers]

    @staticmethod
    def _condition_matches(condition: str | None, values: dict[str, Any]) -> bool:
        if condition is None or not condition.strip():
            return True
        expression = condition.strip()
        if expression.startswith("exists:"):
            key = expression[7:].strip()
            return bool(key) and key in values
        if expression.startswith("equals:"):
            body = expression[7:]
            if "=" not in body:
                return False
            key, expected = body.split("=", 1)
            key = key.strip()
            return bool(key) and str(values.get(key, "")) == expected.strip()
        return False
