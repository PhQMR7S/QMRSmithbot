from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.workflows.actions import ActionRegistry
from qmrsmithbot.workflows.side_effects import (
    AiohttpHttpTransport,
    DeleteMessageActionHandler,
    EditMessageActionHandler,
    HttpActionHandler,
    SendMessageActionHandler,
)


def build_action_registry(session: AsyncSession) -> ActionRegistry:
    registry = ActionRegistry()
    registry.register("action.message", SendMessageActionHandler(session))
    registry.register("action.edit_message", EditMessageActionHandler(session))
    registry.register("action.delete_message", DeleteMessageActionHandler(session))
    registry.register("action.http", HttpActionHandler(AiohttpHttpTransport()))
    return registry
