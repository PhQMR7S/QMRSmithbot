from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from aiogram.types import Update
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.api.dependencies import get_session
from qmrsmithbot.db.models import BotProjectRecord
from qmrsmithbot.db.telegram_runtime_models import TelegramWebhookStateRecord
from qmrsmithbot.telegram.queue import TelegramUpdateQueue
from qmrsmithbot.telegram.webhook import require_telegram_webhook_secret

MAX_TELEGRAM_WEBHOOK_BODY_BYTES = 1_048_576

router = APIRouter(prefix="/api/v1/telegram", tags=["telegram-runtime"])


async def _read_bounded_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid content length") from exc
        if declared < 0 or declared > MAX_TELEGRAM_WEBHOOK_BODY_BYTES:
            raise HTTPException(status_code=413, detail="webhook payload is too large")

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_TELEGRAM_WEBHOOK_BODY_BYTES:
            raise HTTPException(status_code=413, detail="webhook payload is too large")
        body.extend(chunk)
    return bytes(body)


@router.post("/webhook/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def telegram_webhook(
    project_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await require_telegram_webhook_secret(project_id, session, request.headers.get("X-Telegram-Bot-Api-Secret-Token"))

    state = await session.scalar(
        select(TelegramWebhookStateRecord).where(
            TelegramWebhookStateRecord.project_id == project_id,
            TelegramWebhookStateRecord.status == "active",
        )
    )
    project = await session.scalar(
        select(BotProjectRecord.telegram_bot_id).where(BotProjectRecord.id == project_id)
    )
    if state is None or project is None:
        raise HTTPException(status_code=404, detail="webhook is not active")

    raw_body = await _read_bounded_body(request)
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid Telegram update JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Telegram update must be a JSON object")

    try:
        update = Update.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid Telegram update") from exc

    accepted = await TelegramUpdateQueue(session).enqueue(
        project_id=project_id,
        telegram_bot_id=project,
        update_id=update.update_id,
        payload=payload,
    )
    if not accepted:
        return
