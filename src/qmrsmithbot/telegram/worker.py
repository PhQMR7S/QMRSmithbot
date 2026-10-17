from __future__ import annotations

import asyncio
import random
import socket
from typing import Final
from uuid import uuid4

from qmrsmithbot.config import settings
from qmrsmithbot.db.session import SessionFactory
from qmrsmithbot.telegram.execution import (
    NonRetryableTelegramUpdateError,
    RetryableTelegramUpdateError,
    TelegramRuntimeExecutionBoundary,
    TelegramUpdateHandler,
)
from qmrsmithbot.telegram.queue import TelegramUpdateQueue

MAX_RETRY_DELAY_SECONDS: Final[int] = 300


class TelegramRuntimeWorker:
    """Crash-safe, at-least-once consumer for the durable Telegram inbox."""

    def __init__(self, handler: TelegramUpdateHandler, *, worker_id: str | None = None) -> None:
        self.handler = handler
        self.worker_id = worker_id or f"{socket.gethostname()}:{uuid4().hex}"
        self.execution = TelegramRuntimeExecutionBoundary()
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run_once(self) -> bool:
        async with SessionFactory() as session, session.begin():
            item = await TelegramUpdateQueue(session).claim_one(worker_id=self.worker_id)
        if item is None:
            return False

        try:
            await asyncio.wait_for(
                self.execution.execute(item, self.handler),
                timeout=settings.telegram_worker_handler_timeout_seconds,
            )
        except NonRetryableTelegramUpdateError as exc:
            async with SessionFactory() as session, session.begin():
                await TelegramUpdateQueue(session).fail(
                    update_id=item.id,
                    claim_token=item.claim_token,
                    error=f"non-retryable handler error: {type(exc).__name__}",
                    retry_delay_seconds=0,
                    terminal=True,
                )
        except (RetryableTelegramUpdateError, TimeoutError) as exc:
            delay = min(
                MAX_RETRY_DELAY_SECONDS,
                max(1, 2 ** min(item.attempts - 1, 8)) + random.randint(0, 3),
            )
            async with SessionFactory() as session, session.begin():
                await TelegramUpdateQueue(session).fail(
                    update_id=item.id,
                    claim_token=item.claim_token,
                    error=f"retryable handler error: {type(exc).__name__}",
                    retry_delay_seconds=delay,
                )
        except Exception as exc:  # noqa: BLE001 - isolate arbitrary plugin/handler failures
            # Unexpected handler errors must not terminate the consumer loop or
            # strand a claim until lease expiry. Do not persist arbitrary exception
            # messages: they may contain user input or credentials.
            delay = min(
                MAX_RETRY_DELAY_SECONDS,
                max(1, 2 ** min(item.attempts - 1, 8)) + random.randint(0, 3),
            )
            async with SessionFactory() as session, session.begin():
                await TelegramUpdateQueue(session).fail(
                    update_id=item.id,
                    claim_token=item.claim_token,
                    error=f"unexpected handler error: {type(exc).__name__}",
                    retry_delay_seconds=delay,
                )
        else:
            async with SessionFactory() as session, session.begin():
                # A lease may legitimately expire while a slow handler is finishing.
                # Losing the lease is not a worker-fatal condition: another consumer
                # owns the row now, and its completion/failure remains authoritative.
                await TelegramUpdateQueue(session).complete(
                    update_id=item.id,
                    claim_token=item.claim_token,
                )
        return True

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            did_work = await self.run_once()
            if not did_work:
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=settings.telegram_worker_poll_seconds
                    )
                except TimeoutError:
                    continue

    async def shutdown(self) -> None:
        self.stop()
