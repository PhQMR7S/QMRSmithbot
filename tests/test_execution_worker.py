from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Self
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from qmrsmithbot.workflows.execution_store import WorkflowExecutionSnapshot
from qmrsmithbot.workflows.execution_worker import WorkflowResumeWorker


def make_snapshot() -> WorkflowExecutionSnapshot:
    now = datetime.now(UTC)
    return WorkflowExecutionSnapshot(
        id=uuid4(),
        project_id=uuid4(),
        tenant_id=uuid4(),
        update_id=42,
        workflow_version_id=uuid4(),
        workflow_version=7,
        status="running",
        attempts=1,
        visited_nodes=("start",),
        pending_nodes=("send",),
        context_values={"name": "QMR"},
        checkpoint_version=3,
        lease_expires_at=now,
        worker_id="worker-a",
        error=None,
        trace_id="trace-1",
        started_at=now,
        completed_at=None,
    )


class FakeSession:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


@pytest.mark.asyncio
async def test_resume_worker_claims_and_dispatches_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = make_snapshot()
    claimed = AsyncMock(return_value=snapshot)
    processor = AsyncMock()

    class FakeStore:
        def __init__(self, session: object, *, lease_seconds: float) -> None:
            assert lease_seconds == 30

        async def claim_next_resumable(self, *, worker_id: str, now: datetime) -> WorkflowExecutionSnapshot:
            assert worker_id == "worker-a"
            return await claimed()

    monkeypatch.setattr("qmrsmithbot.workflows.execution_worker.WorkflowExecutionStore", FakeStore)
    factory = MagicMock(return_value=FakeSession())
    worker = WorkflowResumeWorker(factory, processor, worker_id="worker-a", lease_seconds=30)

    assert await worker.run_once(now=datetime.now(UTC)) is True
    processor.assert_awaited_once_with(snapshot)
    claimed.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_worker_does_not_dispatch_when_queue_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    processor = AsyncMock()

    class FakeStore:
        def __init__(self, session: object, *, lease_seconds: float) -> None:
            return None

        async def claim_next_resumable(self, *, worker_id: str, now: datetime) -> None:
            return None

    monkeypatch.setattr("qmrsmithbot.workflows.execution_worker.WorkflowExecutionStore", FakeStore)
    factory = MagicMock(return_value=FakeSession())
    worker = WorkflowResumeWorker(factory, processor, worker_id="worker-a")

    assert await worker.run_once(now=datetime.now(UTC)) is False
    processor.assert_not_awaited()


def test_resume_worker_rejects_invalid_configuration() -> None:
    factory = MagicMock()
    processor = AsyncMock()
    for worker_id, poll_interval, lease_seconds in (("", 1, 60), ("worker", 0, 60), ("worker", 1, 0)):
        with pytest.raises(ValueError):
            WorkflowResumeWorker(
                factory,
                processor,
                worker_id=worker_id,
                poll_interval_seconds=poll_interval,
                lease_seconds=lease_seconds,
            )


def test_resume_worker_stops_without_initial_poll() -> None:
    factory = MagicMock()
    processor = AsyncMock()
    worker = WorkflowResumeWorker(factory, processor, worker_id="worker-a")
    stop_event = asyncio.Event()
    stop_event.set()

    asyncio.run(worker.run(stop_event=stop_event))
    factory.assert_not_called()
