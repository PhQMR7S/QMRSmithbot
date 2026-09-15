from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.db.models import BotCredentialRecord
from qmrsmithbot.telegram.provisioning import verify_webhook_secret


async def require_telegram_webhook_secret(
    project_id: UUID,
    session: AsyncSession,
    secret_token: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
) -> None:
    if not secret_token or len(secret_token) > 256:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid webhook secret")
    stored_hash = await session.scalar(
        select(BotCredentialRecord.webhook_secret_hash).where(
            BotCredentialRecord.project_id == project_id
        )
    )
    if stored_hash is None or not verify_webhook_secret(secret_token, stored_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid webhook secret")
