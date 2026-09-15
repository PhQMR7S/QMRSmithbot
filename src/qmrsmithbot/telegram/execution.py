from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from aiogram.types import Update

from qmrsmithbot.telegram.queue import ClaimedTelegramUpdate


class NonRetryableTelegramUpdateError(RuntimeError):
    """Raised when an accepted inbox item can never be processed successfully."""


class RetryableTelegramUpdateError(RuntimeError):
    """Raised when an update may succeed on a later attempt."""


@dataclass(frozen=True, slots=True)
class TelegramRuntimeContext:
    project_id: UUID
    telegram_bot_id: int
    update_id: int
    attempt: int


class TelegramUpdateHandler(Protocol):
    async def handle(
        self,
        *,
        update: Update,
        context: TelegramRuntimeContext,
    ) -> None: ...


class TelegramRuntimeExecutionBoundary:
    """Strict boundary between transport delivery and future workflow dispatch."""

    async def execute(
        self,
        item: ClaimedTelegramUpdate,
        handler: TelegramUpdateHandler,
    ) -> None:
        try:
            update = Update.model_validate(item.payload)
        except Exception as exc:
            raise NonRetryableTelegramUpdateError("persisted Telegram update is invalid") from exc

        context = TelegramRuntimeContext(
            project_id=item.project_id,
            telegram_bot_id=item.telegram_bot_id,
            update_id=item.update_id,
            attempt=item.attempts,
        )
        await handler.handle(update=update, context=context)
