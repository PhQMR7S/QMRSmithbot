from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.auth.models import SessionInfo
from qmrsmithbot.db.models import SessionRecord


class SessionAdministrationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_active(self, user_id: int) -> list[SessionInfo]:
        now = datetime.now(UTC)
        rows = await self.session.execute(
            select(SessionRecord)
            .where(
                SessionRecord.user_id == user_id,
                SessionRecord.revoked_at.is_(None),
                SessionRecord.expires_at > now,
            )
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
        ]

    async def revoke(self, *, user_id: int, session_id: UUID) -> bool:
        record = await self.session.scalar(
            select(SessionRecord).where(
                SessionRecord.id == session_id,
                SessionRecord.user_id == user_id,
            )
        )
        if record is None or record.revoked_at is not None:
            return False
        record.revoked_at = datetime.now(UTC)
        await self.session.flush()
        return True
