from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from qmrsmithbot.workflows.executor import ExecutionContext
from qmrsmithbot.workflows.schema import WorkflowNode


class ActionFailureKind(StrEnum):
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"


class ActionExecutionError(RuntimeError):
    """Base error for action execution."""

    def __init__(self, message: str, *, kind: ActionFailureKind) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Deterministic result metadata; action payloads remain outside logs by default."""

    action_type: str
    external_key: str
    attempt: int
    metadata: dict[str, Any]


class ActionHandler(Protocol):
    async def execute(
        self, *, node: WorkflowNode, context: ExecutionContext, attempt: int
    ) -> ActionResult: ...


class ActionRegistry:
    """Explicit allowlisted action handlers; unknown types never execute."""

    def __init__(self, handlers: dict[str, ActionHandler] | None = None) -> None:
        self._handlers = dict(handlers or {})

    def register(self, action_type: str, handler: ActionHandler) -> None:
        if not action_type or not action_type.startswith("action."):
            raise ValueError("action type must use the action.* namespace")
        if action_type in self._handlers:
            raise ValueError(f"action handler already registered: {action_type}")
        self._handlers[action_type] = handler

    def resolve(self, action_type: str) -> ActionHandler:
        handler = self._handlers.get(action_type)
        if handler is None:
            raise ActionExecutionError(
                f"no action handler registered for node type: {action_type}",
                kind=ActionFailureKind.NON_RETRYABLE,
            )
        return handler


class ActionEngine:
    """Runs one action through an explicit registry with a hard deadline."""

    def __init__(
        self,
        registry: ActionRegistry,
        *,
        max_attempts: int = 3,
        action_timeout_seconds: float = 15.0,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if action_timeout_seconds <= 0:
            raise ValueError("action_timeout_seconds must be positive")
        self.registry = registry
        self.max_attempts = max_attempts
        self.action_timeout_seconds = action_timeout_seconds

    async def execute(
        self, *, node: WorkflowNode, context: ExecutionContext, attempt: int = 1
    ) -> ActionResult:
        if not node.type.startswith("action."):
            raise ActionExecutionError(
                "ActionEngine can only execute action nodes",
                kind=ActionFailureKind.NON_RETRYABLE,
            )
        if not 1 <= attempt <= self.max_attempts:
            raise ActionExecutionError(
                "action attempt is outside the configured retry budget",
                kind=ActionFailureKind.NON_RETRYABLE,
            )

        remaining = context.remaining_seconds()
        timeout = self.action_timeout_seconds
        if remaining is not None:
            timeout = min(timeout, remaining)
        if timeout <= 0:
            raise ActionExecutionError(
                "workflow deadline exceeded before action execution",
                kind=ActionFailureKind.RETRYABLE,
            )

        handler = self.registry.resolve(node.type)
        try:
            return await asyncio.wait_for(
                handler.execute(node=node, context=context, attempt=attempt),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            raise ActionExecutionError(
                f"action timed out: {node.id}", kind=ActionFailureKind.RETRYABLE
            ) from exc
