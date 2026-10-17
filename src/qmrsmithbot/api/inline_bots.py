import asyncio
import json
from typing import Annotated
from uuid import UUID

from aiogram.types import Update
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.api.factory import acknowledge_callback
from qmrsmithbot.api.telegram_webhook import _read_bounded_body
from qmrsmithbot.config import settings
from qmrsmithbot.db.models import BotCredentialRecord
from qmrsmithbot.db.session import get_session
from qmrsmithbot.telegram.inline_runtime import InlineBotError, process_inline_update
from qmrsmithbot.telegram.provisioning import decrypt_bot_token
from qmrsmithbot.telegram.webhook import require_telegram_webhook_secret

router = APIRouter(prefix='/api/v1/telegram/inline', tags=['text-bots'])


@router.post('/{project_id}')
async def inline_webhook(project_id: UUID, request: Request,
        session: Annotated[AsyncSession, Depends(get_session)]):
    if not settings.telegram_inline_runtime_enabled:
        raise HTTPException(status_code=503, detail='Text runtime is unavailable')
    await require_telegram_webhook_secret(project_id, session,
        request.headers.get('X-Telegram-Bot-Api-Secret-Token'))
    try:
        update = Update.model_validate(json.loads(await _read_bounded_body(request)))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail='Invalid update') from exc
    if update.update_id < 0:
        raise HTTPException(status_code=400, detail='Invalid update')
    acknowledgement = None
    if update.callback_query:
        credential = await session.get(BotCredentialRecord, project_id)
        acknowledgement = asyncio.create_task(acknowledge_callback(update.callback_query.id, decrypt_bot_token(credential.token_ciphertext)))
    try:
        response = await process_inline_update(session, project_id, update)
    except (InlineBotError, ValueError) as exc:
        raise HTTPException(status_code=503, detail='Text bot is unavailable') from exc
    finally:
        if acknowledgement is not None:
            await acknowledgement
    return response if response else Response(status_code=204)
