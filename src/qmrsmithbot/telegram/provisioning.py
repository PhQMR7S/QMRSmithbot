from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from uuid import UUID

from aiogram import Bot
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.auth.authorization import AuthorizationService
from qmrsmithbot.auth.models import Permission
from qmrsmithbot.config import settings
from qmrsmithbot.db.models import BotCredentialRecord, BotProjectRecord
from qmrsmithbot.db.telegram_runtime_models import TelegramWebhookStateRecord


class TelegramProvisioningError(RuntimeError):
    pass


class TelegramBotTokenInvalid(TelegramProvisioningError):
    pass


class TelegramBotNotFound(TelegramProvisioningError):
    pass


class TelegramBotAlreadyAssigned(TelegramProvisioningError):
    pass


@dataclass(frozen=True, slots=True)
class ProvisionedBot:
    project_id: UUID
    telegram_bot_id: int
    telegram_username: str | None
    webhook_secret: str


def _credential_cipher() -> Fernet:
    value = settings.telegram_credential_encryption_key.get_secret_value().strip()
    if not value:
        raise TelegramProvisioningError("Telegram credential encryption is not configured")
    try:
        return Fernet(value.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise TelegramProvisioningError("invalid Telegram credential encryption key") from exc


def hash_webhook_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_webhook_secret(raw_secret: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_webhook_secret(raw_secret), stored_hash)


class TelegramBotProvisioningService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def provision(
        self,
        *,
        user_id: int,
        tenant_id: UUID,
        project_id: UUID,
        raw_bot_token: str,
    ) -> ProvisionedBot:
        authorization = AuthorizationService(self.session)
        await authorization.require_permission(
            user_id=user_id, tenant_id=tenant_id, permission=Permission.PROJECT_WRITE
        )
        token = raw_bot_token.strip()
        if not token or len(token) > 512:
            raise TelegramBotTokenInvalid("invalid Telegram bot token")

        # Do not hold a project row lock while making a network request to Telegram.
        await self.session.rollback()
        try:
            bot = Bot(token=token)
            me = await bot.get_me()
        except Exception as exc:
            raise TelegramBotTokenInvalid("Telegram rejected the bot token") from exc
        finally:
            if "bot" in locals():
                await bot.session.close()

        project = await self.session.scalar(
            select(BotProjectRecord)
            .where(BotProjectRecord.id == project_id, BotProjectRecord.tenant_id == tenant_id)
            .with_for_update()
        )
        if project is None:
            raise TelegramBotNotFound("project was not found")

        assigned = await self.session.scalar(
            select(BotProjectRecord).where(
                BotProjectRecord.telegram_bot_id == me.id,
                BotProjectRecord.id != project_id,
            )
        )
        if assigned is not None:
            raise TelegramBotAlreadyAssigned("Telegram bot is already assigned to another project")

        credential = await self.session.scalar(
            select(BotCredentialRecord)
            .where(BotCredentialRecord.project_id == project_id)
            .with_for_update()
        )
        cipher = _credential_cipher()
        webhook_secret = secrets.token_urlsafe(32)
        encrypted_token = cipher.encrypt(token.encode("utf-8")).decode("ascii")

        try:
            async with self.session.begin_nested():
                if credential is None:
                    credential = BotCredentialRecord(
                        project_id=project_id,
                        token_ciphertext=encrypted_token,
                        token_last4=token[-4:],
                        token_version=1,
                        webhook_secret_hash=hash_webhook_secret(webhook_secret),
                    )
                    self.session.add(credential)
                else:
                    credential.token_ciphertext = encrypted_token
                    credential.token_last4 = token[-4:]
                    credential.token_version += 1
                    credential.webhook_secret_hash = hash_webhook_secret(webhook_secret)

                project.telegram_bot_id = me.id
                project.telegram_username = me.username
                await self.session.flush()
        except IntegrityError as exc:
            if "telegram_bot_id" in str(exc.orig):
                raise TelegramBotAlreadyAssigned(
                    "Telegram bot is already assigned to another project"
                ) from exc
            raise

        return ProvisionedBot(
            project_id=project_id,
            telegram_bot_id=me.id,
            telegram_username=me.username,
            webhook_secret=webhook_secret,
        )

    async def rotate_webhook_secret(
        self, *, user_id: int, tenant_id: UUID, project_id: UUID
    ) -> str:
        authorization = AuthorizationService(self.session)
        await authorization.require_permission(
            user_id=user_id, tenant_id=tenant_id, permission=Permission.PROJECT_WRITE
        )
        webhook_state = await self.session.scalar(
            select(TelegramWebhookStateRecord.status).where(
                TelegramWebhookStateRecord.project_id == project_id
            )
        )
        if webhook_state == "active":
            raise TelegramProvisioningError(
                "deactivate the Telegram webhook before rotating its secret"
            )
        credential = await self.session.scalar(
            select(BotCredentialRecord)
            .join(BotProjectRecord, BotProjectRecord.id == BotCredentialRecord.project_id)
            .where(
                BotCredentialRecord.project_id == project_id,
                BotProjectRecord.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if credential is None:
            raise TelegramBotNotFound("bot credentials were not found")
        secret = secrets.token_urlsafe(32)
        credential.webhook_secret_hash = hash_webhook_secret(secret)
        await self.session.flush()
        return secret

    async def disconnect(
        self, *, user_id: int, tenant_id: UUID, project_id: UUID
    ) -> None:
        authorization = AuthorizationService(self.session)
        await authorization.require_permission(
            user_id=user_id, tenant_id=tenant_id, permission=Permission.PROJECT_WRITE
        )
        project = await self.session.scalar(
            select(BotProjectRecord)
            .where(BotProjectRecord.id == project_id, BotProjectRecord.tenant_id == tenant_id)
            .with_for_update()
        )
        if project is None:
            raise TelegramBotNotFound("project was not found")
        credential = await self.session.scalar(
            select(BotCredentialRecord).where(BotCredentialRecord.project_id == project_id)
        )
        if credential is not None:
            await self.session.delete(credential)
        project.telegram_bot_id = None
        project.telegram_username = None
        await self.session.flush()
