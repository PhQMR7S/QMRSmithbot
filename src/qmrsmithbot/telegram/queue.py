from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.db.telegram_runtime_models import TelegramUpdateInboxRecord


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
        statement = (
            insert(TelegramUpdateInboxRecord)
            .values(
                project_id=project_id,
                telegram_bot_id=telegram_bot_id,
                update_id=update_id,
                payload=payload,
                status="queued",
                attempts=0,
                received_at=datetime.now(timezone.utc),
                available_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_nothing(
                constraint="uq_telegram_update_project_update"
            )
        )
        result = await self.session.execute(statement)
        return result.rowcount == 1
