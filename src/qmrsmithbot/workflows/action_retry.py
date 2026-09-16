from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.db.workflow_runtime_models import ActionLedgerRecord


@dataclass(frozen=True, slots=True)
class RetrySchedule:
    ledger_id: UUID
    attempt: int
    available_at: datetime
    delay_seconds: float


class ActionRetryScheduler:
    """Persist and claim retryable action attempts using durable timestamps."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        base_delay_seconds: float = 2.0,
        max_delay_seconds: float = 300.0,
    ) -> None:
        if base_delay_seconds <= 0 or max_delay_seconds <= 0:
            raise ValueError("retry delays must be positive")
        if base_delay_seconds > max_delay_seconds:
            raise ValueError("base retry delay must not exceed maximum retry delay")
        self.session = session
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds

    def delay_for_attempt(self, attempt: int) -> float:
        """Return the capped delay assigned to a future attempt number."""
        if attempt < 1:
            raise ValueError("attempt must be positive")
        return min(self.base_delay_seconds * (2 ** (attempt - 1)), self.max_delay_seconds)

    async def schedule(self, *, ledger_id: UUID) -> RetrySchedule | None:
        """Schedule one retryable failed ledger record for a future attempt."""
        row = await self.session.scalar(
            select(ActionLedgerRecord)
            .where(
                ActionLedgerRecord.id == ledger_id,
                ActionLedgerRecord.status == "failed",
                ActionLedgerRecord.retryable.is_(True),
                ActionLedgerRecord.available_at.is_(None),
            )
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None

        delay_seconds = self.delay_for_attempt(row.attempt)
        available_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        row.available_at = available_at
        row.started_at = None
        row.completed_at = None
        await self.session.flush()
        return RetrySchedule(
            ledger_id=row.id,
            attempt=row.attempt,
            available_at=available_at,
            delay_seconds=delay_seconds,
        )

    async def claim_due(
        self,
        *,
        ledger_id: UUID,
        now: datetime | None = None,
    ) -> ActionLedgerRecord | None:
        """Atomically claim a retry whose durable availability time has arrived."""
        current_time = now or datetime.now(UTC)
        row = await self.session.scalar(
            select(ActionLedgerRecord)
            .where(
                ActionLedgerRecord.id == ledger_id,
                ActionLedgerRecord.status == "failed",
                ActionLedgerRecord.retryable.is_(True),
                ActionLedgerRecord.available_at.is_not(None),
                ActionLedgerRecord.available_at <= current_time,
            )
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        row.status = "running"
        row.started_at = current_time
        row.available_at = None
        row.error = None
        await self.session.flush()
        return row
