from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from qmrsmithbot.telegram.dispatcher import DispatchPlan
from qmrsmithbot.workflows.schema import WorkflowNode


@dataclass(slots=True)
class ExecutionContext:
    values: dict[str, Any] = field(default_factory=dict)
    visited: list[str] = field(default_factory=list)
    steps: int = 0


Handler = Callable[[WorkflowNode, ExecutionContext], Awaitable[None]]


class WorkflowExecutionError(RuntimeError):
    """Raised when a workflow cannot be executed safely."""


class WorkflowLimitExceeded(WorkflowExecutionError):
    """Raised when a workflow exceeds its execution budget."""


class WorkflowExecutor:
    """Bounded deterministic graph executor; side effects live behind handlers."""

    def __init__(self, handlers: dict[str, Handler] | None = None, *, max_steps: int = 1000) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be positive")
        self.handlers = handlers or {}
        self.max_steps = max_steps

    async def run(
        self,
        plan: DispatchPlan,
        context: ExecutionContext | None = None,
    ) -> ExecutionContext:
        execution = context or ExecutionContext()
        nodes = {node.id: node for node in plan.definition.nodes}
        outgoing: dict[str, list[tuple[str, str | None]]] = {}
        for edge in plan.definition.edges:
            outgoing.setdefault(edge.source, []).append((edge.target, edge.condition))

        matched = {trigger.node_id for trigger in plan.triggers}
        queue = list(matched)
        while queue:
            node_id = queue.pop(0)
            if node_id in execution.visited:
                continue
            node = nodes.get(node_id)
            if node is None:
                raise WorkflowExecutionError(f"unknown node: {node_id}")
            execution.steps += 1
            if execution.steps > self.max_steps:
                raise WorkflowLimitExceeded("workflow execution step limit exceeded")

            handler = self.handlers.get(node.type)
            if handler is None and not node.type.startswith("trigger."):
                raise WorkflowExecutionError(f"no handler registered for node type: {node.type}")
            if handler is not None:
                await handler(node, execution)
            execution.visited.append(node_id)

            for target, condition in outgoing.get(node_id, []):
                if self._condition_matches(condition, execution.values):
                    queue.append(target)
        return execution

    @staticmethod
    def _condition_matches(condition: str | None, values: dict[str, Any]) -> bool:
        if condition is None or not condition.strip():
            return True
        expression = condition.strip()
        if expression.startswith("exists:"):
            key = expression[7:].strip()
            return key in values
        if expression.startswith("equals:"):
            body = expression[7:]
            if "=" not in body:
                return False
            key, expected = body.split("=", 1)
            return str(values.get(key.strip(), "")) == expected.strip()
        return False
