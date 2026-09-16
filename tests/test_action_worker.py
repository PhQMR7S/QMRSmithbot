from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import ClassVar, Self
from uuid import uuid4

import pytest

from qmrsmithbot.workflows.action_ledger import ActionLedgerEntry
from qmrsmithbot.workflows.action_worker import ActionRetryWorker


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeLedger:
    recovered: ClassVar[list[ActionLedgerEntry]] = []
    claimed: ClassVar[list[ActionLedgerEntry]] = []
    calls: ClassVar[list[tuple[str, object]]] = []

    def __init__(self, session, *, lease_seconds: float) -> None:
        self.calls.append(("ledger_init", lease_seconds))

    async def recover_expired_lease_entries(self, *, now: datetime):
        self.calls.append(("recover", now))
        return list(self.recovered)

    async def claim_due_batch(self, *, limit: int, now: datetime):
        self.calls.append(("claim", (limit, now)))
        return list(self.claimed)


class FakeScheduler:
    calls: ClassVar[list[object]] = []

    def __init__(self, session, **kwargs) -> None:
        self.calls.append(("init", kwargs))

    async def schedule(self, *, ledger_id):
        self.calls.append(("schedule", ledger_id))
        return object()


def make_entry(*, sequence: int = 1) -> ActionLedgerEntry:
    now = datetime.now(UTC)
    return ActionLedgerEntry(
        id=uuid4(),
        execution_id=uuid4(),
        tenant_id=uuid4(),
        project_id=uuid4(),
        node_id=f"node-{sequence}",
        action_type="action.message",
        idempotency_key=f"key-{sequence}",
        sequence=sequence,
        status="running",
        attempt=2,
        retryable=True,
        result_metadata={},
        error="lease expired",
        completed_at=None,
        lease_expires_at=now - timedelta(seconds=1),
    )


def test_worker_rejects_invalid_configuration() -> None:
    async def processor(entry: ActionLedgerEntry) -> None:
        return None

    with pytest.raises(ValueError):
        ActionRetryWorker(lambda: None, processor, batch_size=0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ActionRetryWorker(lambda: None, processor, poll_interval_seconds=0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ActionRetryWorker(lambda: None, processor, lease_seconds=0)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_run_once_recovers_schedules_claims_commits_and_dispatches(monkeypatch) -> None:
    import qmrsmithbot.workflows.action_worker as module

    session = FakeSession()
    recovered = make_entry(sequence=1)
    claimed = make_entry(sequence=2)
    FakeLedger.recovered = [recovered]
    FakeLedger.claimed = [claimed]
    FakeLedger.calls = []
    FakeScheduler.calls = []

    monkeypatch.setattr(module, "ActionLedgerService", FakeLedger)
    monkeypatch.setattr(module, "ActionRetryScheduler", FakeScheduler)

    class Factory:
        def __call__(self):
            return session

    dispatched: list[ActionLedgerEntry] = []

    async def processor(entry: ActionLedgerEntry) -> None:
        dispatched.append(entry)

    worker = ActionRetryWorker(
        Factory(),
        processor,
        batch_size=3,
        poll_interval_seconds=0.01,
        lease_seconds=45,
        retry_base_delay_seconds=2,
        retry_max_delay_seconds=30,
    )
    now = datetime.now(UTC)
    count = await worker.run_once(now=now)

    assert count == 1
    assert dispatched == [claimed]
    assert session.committed is True
    assert ("recover", now) in FakeLedger.calls
    assert ("claim", (3, now)) in FakeLedger.calls
    assert ("schedule", recovered.id) in FakeScheduler.calls


@pytest.mark.asyncio
async def test_run_stops_cleanly_when_event_is_set(monkeypatch) -> None:
    import qmrsmithbot.workflows.action_worker as module

    class EmptyLedger(FakeLedger):
        async def recover_expired_lease_entries(self, *, now: datetime):
            return []

        async def claim_due_batch(self, *, limit: int, now: datetime):
            return []

    monkeypatch.setattr(module, "ActionLedgerService", EmptyLedger)
    monkeypatch.setattr(module, "ActionRetryScheduler", FakeScheduler)

    session = FakeSession()

    class Factory:
        def __call__(self):
            return session

    async def processor(entry: ActionLedgerEntry) -> None:
        raise AssertionError("no entry should be dispatched")

    stop_event = asyncio.Event()
    stop_event.set()
    worker = ActionRetryWorker(Factory(), processor, poll_interval_seconds=0.01)

    await worker.run(stop_event=stop_event)
    assert session.committed is False
