from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
from uuid import UUID

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.config import settings
from qmrsmithbot.db.models import BotCredentialRecord


class TelegramClientError(RuntimeError):
    pass


class TelegramCredentialsNotFound(TelegramClientError):
    pass


def _decrypt_token(ciphertext: str) -> str:
    key = settings.telegram_credential_encryption_key.get_secret_value().strip()
    if not key:
        raise TelegramClientError("Telegram credential encryption is not configured")
    try:
        plaintext = Fernet(key.encode("ascii")).decrypt(ciphertext.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise TelegramClientError("Telegram credential encryption key is invalid") from exc
    except Exception as exc:
        raise TelegramClientError("Telegram bot credential could not be decrypted") from exc
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TelegramClientError("Telegram bot credential is corrupted") from exc


class TelegramBotClientFactory:
    def __init__(self, session: AsyncSession, *, timeout: float = 15.0) -> None:
        self.session = session
        self.timeout = timeout

    async def _token(self, project_id: UUID) -> str:
        credential = await self.session.scalar(
            select(BotCredentialRecord.token_ciphertext).where(
                BotCredentialRecord.project_id == project_id
            )
        )
        if credential is None:
            raise TelegramCredentialsNotFound("Telegram bot credentials were not found")
        return _decrypt_token(credential)

    @asynccontextmanager
    async def bot(self, project_id: UUID) -> AsyncIterator[Bot]:
        token = await self._token(project_id)
        api_session = AiohttpSession(timeout=self.timeout)
        bot = Bot(token=token, session=api_session)
        try:
            yield bot
        finally:
            await bot.session.close()
