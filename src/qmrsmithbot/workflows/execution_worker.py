from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from qmrsmithbot.workflows.execution_store import (
    WorkflowExecutionSnapshot,
    WorkflowExecutionStore,
)


WorkflowExecutionProcessor = Callable[[WorkflowExecutionSnapshot], Awaitable[None]]


class WorkflowResumeWorker:
    """Claim durable failed/expired executions and dispatch them for resume."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        processor: WorkflowExecutionProcessor,
        *,
        worker_id: str,
        poll_interval_seconds: float = 1.0,
        lease_seconds: float = 60.0,
    ) -> None:
        if not worker_id or len(worker_id) > 128:
            raise ValueError("worker_id must be non-empty and at most 128 characters")
        if poll_interval_seconds <= 0:
            raise ValueError("poll interval must be positive")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.session_factory = session_factory
        self.processor = processor
        self.worker_id = worker_id
        self.poll_interval_seconds = poll_interval_seconds
        self.lease_seconds = lease_seconds

    async def run_once(self, *, now: datetime | None = None) -> bool:
        current_time = now or datetime.now(UTC)
        async with self.session_factory() as session:
            store = WorkflowExecutionStore(session, lease_seconds=self.lease_seconds)
            execution = await store.claim_next_resumable(worker_id=self.worker_id, now=current_time)
            if execution is None:
                await session.rollback()
                return False
            await session.commit()
        await self.processor(execution)
        return True

    async def run(self, *, stop_event: asyncio.Event | None = None) -> None:
        event = stop_event or asyncio.Event()
        while not event.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(event.wait(), timeout=self.poll_interval_seconds)
            except TimeoutError:
                continue
