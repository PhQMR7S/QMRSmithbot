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
    """Compute and persist retry availability for retryable action failures."""

    def __init__(self, session: AsyncSession, *, base_delay_seconds: float = 2.0, max_delay_seconds: float = 300.0) -> None:
        if base_delay_seconds <= 0 or max_delay_seconds <= 0:
            raise ValueError("retry delays must be positive")
        if base_delay_seconds > max_delay_seconds:
            raise ValueError("base retry delay must not exceed maximum retry delay")
        self.session = session
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds

    def delay_for_attempt(self, attempt: int) -> float:
        if attempt < 1:
            raise ValueError("attempt must be positive")
        return min(self.base_delay_seconds * (2 ** (attempt - 1)), self.max_delay_seconds)

    async def schedule(self, *, ledger_id: UUID) -> RetrySchedule | None:
        row = await self.session.scalar(
            select(ActionLedgerRecord)
            .where(ActionLedgerRecord.id == ledger_id)
            .with_for_update()
        )
        if row is None or row.status != "failed":
            return None
        delay_seconds = self.delay_for_attempt(row.attempt)
        available_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        row.started_at = None
        row.completed_at = None
        row.error = row.error
        await self.session.flush()
        return RetrySchedule(
            ledger_id=row.id,
            attempt=row.attempt,
            available_at=available_at,
            delay_seconds=delay_seconds,
        )
