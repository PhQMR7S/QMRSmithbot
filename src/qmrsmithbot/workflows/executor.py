from __future__ import annotations

from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from qmrsmithbot.workflows.schema import WorkflowDefinition, WorkflowNode


@dataclass
class ExecutionContext:
    values: dict[str, Any] = field(default_factory=dict)
    visited: list[str] = field(default_factory=list)


Handler = Callable[[WorkflowNode, ExecutionContext], Awaitable[None]]


class WorkflowExecutionError(RuntimeError):
    """Raised when a workflow cannot be executed safely."""


class WorkflowExecutor:
    """Deterministic, bounded workflow execution independent of Telegram adapters."""

    def __init__(self, handlers: dict[str, Handler] | None = None, *, max_steps: int = 1000) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be positive")
        self.handlers = handlers or {}
        self.max_steps = max_steps

    async def run(self, workflow: WorkflowDefinition, context: ExecutionContext) -> ExecutionContext:
        nodes = {node.id: node for node in workflow.nodes}
        outgoing: dict[str, list[str]] = {}
        for edge in workflow.edges:
            outgoing.setdefault(edge.source, []).append(edge.target)

        queue = deque(node.id for node in workflow.nodes if node.type.startswith("trigger."))
        steps = 0
        while queue:
            node_id = queue.popleft()
            if node_id in context.visited:
                continue
            node = nodes.get(node_id)
            if node is None:
                raise WorkflowExecutionError(f"unknown node: {node_id}")

            steps += 1
            if steps > self.max_steps:
                raise WorkflowExecutionError("workflow execution step limit exceeded")

            handler = self.handlers.get(node.type)
            if handler is None and not node.type.startswith("trigger."):
                raise WorkflowExecutionError(f"no handler registered for node type: {node.type}")
            if handler is not None:
                await handler(node, context)

            context.visited.append(node_id)
            queue.extend(outgoing.get(node_id, ()))

        return context
