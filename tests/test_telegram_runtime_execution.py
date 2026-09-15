from uuid import uuid4

import pytest

from qmrsmithbot.telegram.execution import (
    NonRetryableTelegramUpdateError,
    TelegramRuntimeExecutionBoundary,
)
from qmrsmithbot.telegram.queue import ClaimedTelegramUpdate


class RecordingHandler:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    async def handle(self, *, update, context) -> None:
        self.calls.append((update.update_id, context.attempt))


def _item(payload: dict) -> ClaimedTelegramUpdate:
    return ClaimedTelegramUpdate(
        id=uuid4(),
        project_id=uuid4(),
        telegram_bot_id=123,
        update_id=42,
        payload=payload,
        attempts=2,
        claim_token="worker:claim",
    )


@pytest.mark.asyncio
async def test_execution_boundary_validates_and_forwards_update() -> None:
    handler = RecordingHandler()
    payload = {"update_id": 42}

    await TelegramRuntimeExecutionBoundary().execute(_item(payload), handler)

    assert handler.calls == [(42, 2)]


@pytest.mark.asyncio
async def test_execution_boundary_rejects_invalid_persisted_update() -> None:
    handler = RecordingHandler()

    with pytest.raises(NonRetryableTelegramUpdateError):
        await TelegramRuntimeExecutionBoundary().execute(
            _item({"update_id": "not-an-integer"}), handler
        )

    assert handler.calls == []
