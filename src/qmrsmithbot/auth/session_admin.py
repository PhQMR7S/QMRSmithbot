from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.auth.models import SessionInfo
from qmrsmithbot.db.models import SessionRecord


class SessionAdministrationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_active(self, user_id: int) -> list[SessionInfo]:
        rows = await self.session.execute(
            select(SessionRecord)
            .where(SessionRecord.user_id == user_id)
            .order_by(SessionRecord.created_at.desc())
        )
        return [
            SessionInfo(
                id=record.id,
                created_at=record.created_at,
                last_seen_at=record.last_seen_at,
                expires_at=record.expires_at,
                revoked_at=record.revoked_at,
                user_agent=record.user_agent,
                ip_address=record.ip_address,
            )
            for record in rows.scalars()
            if record.revoked_at is None and record.expires_at > record.last_seen_at
        ]

    async def revoke(self, *, user_id: int, session_id: UUID) -> None:
        record = await self.session.scalar(
            select(SessionRecord).where(
                SessionRecord.id == session_id,
                SessionRecord.user_id == user_id,
            )
        )
        if record is not None and record.revoked_at is None:
            from datetime import UTC, datetime

            record.revoked_at = datetime.now(UTC)
            await self.session.flush()
