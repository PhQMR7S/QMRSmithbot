from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.config import settings
from qmrsmithbot.db.telegram_runtime_models import TelegramUpdateInboxRecord


@dataclass(frozen=True, slots=True)
class ClaimedTelegramUpdate:
    id: UUID
    project_id: UUID
    telegram_bot_id: int
    update_id: int
    payload: dict
    attempts: int
    claim_token: str


class TelegramUpdateQueue:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(
        self,
        *,
        project_id: UUID,
        telegram_bot_id: int,
        update_id: int,
        payload: dict,
    ) -> bool:
        now = datetime.now(UTC)
        statement = (
            insert(TelegramUpdateInboxRecord)
            .values(
                project_id=project_id,
                telegram_bot_id=telegram_bot_id,
                update_id=update_id,
                payload=payload,
                status="queued",
                attempts=0,
                received_at=now,
                available_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_telegram_update_project_update")
        )
        result = await self.session.execute(statement)
        return result.rowcount == 1

    async def claim_one(self, *, worker_id: str) -> ClaimedTelegramUpdate | None:
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=settings.telegram_worker_lease_seconds)
        claim_token = f"{worker_id}:{uuid4().hex}"
        candidate = await self.session.scalar(
            select(TelegramUpdateInboxRecord)
            .where(
                or_(
                    (TelegramUpdateInboxRecord.status == "queued")
                    & (TelegramUpdateInboxRecord.available_at <= now),
                    (TelegramUpdateInboxRecord.status == "processing")
                    & (TelegramUpdateInboxRecord.lease_until < now),
                )
            )
            .order_by(TelegramUpdateInboxRecord.available_at, TelegramUpdateInboxRecord.received_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if candidate is None:
            return None

        candidate.status = "processing"
        candidate.attempts += 1
        candidate.claimed_by = claim_token
        candidate.lease_until = lease_until
        await self.session.flush()
        return ClaimedTelegramUpdate(
            id=candidate.id,
            project_id=candidate.project_id,
            telegram_bot_id=candidate.telegram_bot_id,
            update_id=candidate.update_id,
            payload=candidate.payload,
            attempts=candidate.attempts,
            claim_token=claim_token,
        )

    async def complete(self, *, update_id: UUID, claim_token: str) -> bool:
        result = await self.session.execute(
            update(TelegramUpdateInboxRecord)
            .where(
                TelegramUpdateInboxRecord.id == update_id,
                TelegramUpdateInboxRecord.status == "processing",
                TelegramUpdateInboxRecord.claimed_by == claim_token,
            )
            .values(
                status="completed",
                processed_at=datetime.now(UTC),
                claimed_by=None,
                lease_until=None,
                last_error=None,
            )
        )
        return result.rowcount == 1

    async def fail(
        self,
        *,
        update_id: UUID,
        claim_token: str,
        error: str,
        retry_delay_seconds: int,
        terminal: bool = False,
    ) -> bool:
        safe_error = error[:500]
        now = datetime.now(UTC)
        row = await self.session.scalar(
            select(TelegramUpdateInboxRecord)
            .where(
                TelegramUpdateInboxRecord.id == update_id,
                TelegramUpdateInboxRecord.status == "processing",
                TelegramUpdateInboxRecord.claimed_by == claim_token,
            )
            .with_for_update()
        )
        if row is None:
            return False
        terminal = terminal or row.attempts >= settings.telegram_worker_max_attempts
        row.status = "failed" if terminal else "queued"
        row.available_at = now + timedelta(seconds=max(0, retry_delay_seconds))
        row.claimed_by = None
        row.lease_until = None
        row.last_error = safe_error
        if terminal:
            row.processed_at = now
        await self.session.flush()
        return True
