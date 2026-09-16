from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from qmrsmithbot.workflows.action_ledger import ActionLedgerEntry, ActionLedgerService
from qmrsmithbot.workflows.action_retry import ActionRetryScheduler


class DurableActionProcessor(Protocol):
    async def __call__(self, entry: ActionLedgerEntry) -> None: ...


class ActionRetryWorker:
    """Poll durable retry state and dispatch atomically claimed actions."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        processor: DurableActionProcessor,
        *,
        batch_size: int = 10,
        poll_interval_seconds: float = 1.0,
        lease_seconds: float = 60.0,
        retry_base_delay_seconds: float = 2.0,
        retry_max_delay_seconds: float = 300.0,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if poll_interval_seconds <= 0:
            raise ValueError("poll interval must be positive")
        self.session_factory = session_factory
        self.processor = processor
        self.batch_size = batch_size
        self.poll_interval_seconds = poll_interval_seconds
        self.lease_seconds = lease_seconds
        self.retry_base_delay_seconds = retry_base_delay_seconds
        self.retry_max_delay_seconds = retry_max_delay_seconds

    async def run_once(self, *, now: datetime | None = None) -> int:
        """Recover expired leases, schedule them, claim due retries, and dispatch them."""
        current_time = now or datetime.now(UTC)
        async with self.session_factory() as session:
            ledger = ActionLedgerService(session, lease_seconds=self.lease_seconds)
            scheduler = ActionRetryScheduler(
                session,
                base_delay_seconds=self.retry_base_delay_seconds,
                max_delay_seconds=self.retry_max_delay_seconds,
            )
            recovered = await ledger.recover_expired_lease_entries(now=current_time)
            for entry in recovered:
                await scheduler.schedule(ledger_id=entry.id)
            claimed = await ledger.claim_due_batch(limit=self.batch_size, now=current_time)
            await session.commit()

        for entry in claimed:
            await self.processor(entry)
        return len(claimed)

    async def run(
        self,
        *,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Run until cancellation or an optional stop event is set."""
        event = stop_event or asyncio.Event()
        while not event.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(event.wait(), timeout=self.poll_interval_seconds)
            except TimeoutError:
                continue


# Keep the callable alias discoverable for dependency-injection registries.
ActionRetryProcessor = Callable[[ActionLedgerEntry], Awaitable[None]]
