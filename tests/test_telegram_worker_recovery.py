"""Regression coverage for unexpected errors in the durable inbox worker."""
from typing import ClassVar
from uuid import uuid4

import pytest

from qmrsmithbot.telegram.execution import (
    NonRetryableTelegramUpdateError,
    RetryableTelegramUpdateError,
)
from qmrsmithbot.telegram.queue import ClaimedTelegramUpdate
from qmrsmithbot.telegram.worker import TelegramRuntimeWorker


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def begin(self):
        return FakeSession()


class FakeQueue:
    failures: ClassVar[list[dict]] = []
    item = None

    def __init__(self, session):
        pass

    async def claim_one(self, *, worker_id):
        return self.item

    async def fail(self, **kwargs):
        self.failures.append(kwargs)


class ExplodingBoundary:
    def __init__(self, error):
        self.error = error

    async def execute(self, item, handler):
        raise self.error


@pytest.mark.parametrize(
    ("error", "expected_message", "terminal"),
    [
        (RuntimeError("secret user-provided payload"), "unexpected handler error: RuntimeError", False),
        (RetryableTelegramUpdateError("secret token"), "retryable handler error: RetryableTelegramUpdateError", False),
        (NonRetryableTelegramUpdateError("secret token"), "non-retryable handler error: NonRetryableTelegramUpdateError", True),
    ],
)
@pytest.mark.asyncio
async def test_handler_errors_do_not_leak_payload(monkeypatch, error, expected_message, terminal):
    from qmrsmithbot.telegram import worker as module

    FakeQueue.failures = []
    FakeQueue.item = ClaimedTelegramUpdate(
        id=uuid4(),
        project_id=uuid4(),
        telegram_bot_id=123,
        update_id=42,
        payload={"update_id": 42},
        attempts=1,
        claim_token="worker:claim",
    )
    monkeypatch.setattr(module, "SessionFactory", FakeSession)
    monkeypatch.setattr(module, "TelegramUpdateQueue", FakeQueue)
    worker = TelegramRuntimeWorker(handler=None)
    worker.execution = ExplodingBoundary(error)

    assert await worker.run_once() is True
    assert len(FakeQueue.failures) == 1
    failure = FakeQueue.failures[0]
    assert failure["update_id"] == FakeQueue.item.id
    assert failure["claim_token"] == FakeQueue.item.claim_token
    assert failure["retry_delay_seconds"] >= (0 if terminal else 1)
    assert failure.get("terminal", False) is terminal
    assert failure["error"] == expected_message
    assert "secret" not in failure["error"]
