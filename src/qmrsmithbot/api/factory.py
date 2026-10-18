import asyncio
import hmac
import json
import logging
import re
from typing import Annotated

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Update
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from qmrsmithbot.api.telegram_webhook import _read_bounded_body
from qmrsmithbot.config import settings
from qmrsmithbot.factory.processor import FactoryProcessor

router = APIRouter(prefix='/api/v1/factory', tags=['telegram-factory'])
logger = logging.getLogger(__name__)


def get_factory_processor():
    return FactoryProcessor()


async def acknowledge_callback(callback_id, token=None):
    bot = Bot(token or settings.telegram_factory_bot_token.get_secret_value(), session=AiohttpSession(timeout=0.6))
    try:
        async with asyncio.timeout(0.6):
            await bot.answer_callback_query(callback_id)
    except (TelegramAPIError, OSError, TimeoutError):
        logger.warning('Factory callback acknowledgement failed')
    finally:
        await bot.session.close()


async def delete_sensitive_message(update):
    message = update.message
    if (message is None or message.chat.type != 'private' or not message.text
            or not re.search(r'\b[0-9]{5,16}:[A-Za-z0-9_-]{20,}\b', message.text)):
        return
    bot = Bot(settings.telegram_factory_bot_token.get_secret_value(), session=AiohttpSession(timeout=3))
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except (TelegramAPIError, OSError, TimeoutError):
        logger.warning('Sensitive factory message deletion failed')
    finally:
        await bot.session.close()


@router.post('/webhook')
async def factory_webhook(
    request: Request,
    processor: Annotated[FactoryProcessor, Depends(get_factory_processor)],
):
    if not settings.telegram_factory_enabled:
        raise HTTPException(status_code=503, detail='Factory interface is not enabled')
    expected = settings.telegram_factory_webhook_secret.get_secret_value()
    supplied = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if not expected or len(supplied) > 256 or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail='Invalid factory webhook secret')
    try:
        update = Update.model_validate(json.loads(await _read_bounded_body(request)))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail='Invalid Telegram update') from exc
    if update.update_id < 0:
        raise HTTPException(status_code=400, detail='Invalid Telegram update ID')
    acknowledgement = asyncio.create_task(acknowledge_callback(update.callback_query.id)) if update.callback_query else None
    try:
        result = await processor.process(update)
    finally:
        if acknowledgement is not None:
            await acknowledgement
    await delete_sensitive_message(update)
    return result if result is not None else Response(status_code=204)
