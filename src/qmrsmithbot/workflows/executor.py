from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from qmrsmithbot.workflows.schema import WorkflowDefinition, WorkflowNode


@dataclass
class ExecutionContext:
    values: dict[str, Any] = field(default_factory=dict)
    visited: list[str] = field(default_factory=list)


Handler = Callable[[WorkflowNode, ExecutionContext], Awaitable[None]]


class WorkflowExecutor:
    """Small deterministic execution core; Telegram/HTTP adapters live outside it."""

    def __init__(self, handlers: dict[str, Handler] | None = None) -> None:
        self.handlers = handlers or {}

    async def run(self, workflow: WorkflowDefinition, context: ExecutionContext) -> ExecutionContext:
        outgoing: dict[str, list[str]] = {}
        for edge in workflow.edges:
            outgoing.setdefault(edge.source, []).append(edge.target)

        queue = [node.id for node in workflow.nodes if node.type.startswith("trigger.")]
        nodes = {node.id: node for node in workflow.nodes}

        while queue:
            node_id = queue.pop(0)
            if node_id in context.visited:
                continue
            node = nodes[node_id]
            handler = self.handlers.get(node.type)
            if handler is not None:
                await handler(node, context)
            context.visited.append(node_id)
            queue.extend(outgoing.get(node_id, []))

        return context
