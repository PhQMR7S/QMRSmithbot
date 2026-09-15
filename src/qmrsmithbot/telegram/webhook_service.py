from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.auth.authorization import AuthorizationService
from qmrsmithbot.auth.models import Permission
from qmrsmithbot.config import settings
from qmrsmithbot.db.models import BotCredentialRecord, BotProjectRecord
from qmrsmithbot.db.telegram_runtime_models import TelegramWebhookStateRecord
from qmrsmithbot.telegram.client import TelegramBotClientFactory
from qmrsmithbot.telegram.provisioning import hash_webhook_secret


class TelegramWebhookError(RuntimeError):
    pass


class TelegramWebhookNotReady(TelegramWebhookError):
    pass


@dataclass(frozen=True, slots=True)
class WebhookActivationResult:
    project_id: UUID
    webhook_url: str
    webhook_secret: str


class TelegramWebhookService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _webhook_url(project_id: UUID) -> str:
        base = settings.telegram_webhook_base_url.strip().rstrip("/")
        if not base:
            raise TelegramWebhookNotReady("Telegram webhook base URL is not configured")
        parsed = urlparse(base)
        if parsed.scheme != "https" or not parsed.netloc:
            raise TelegramWebhookNotReady("Telegram webhook base URL must be HTTPS")
        return f"{base}/api/v1/telegram/webhook/{project_id}"

    async def activate(
        self, *, user_id: int, tenant_id: UUID, project_id: UUID
    ) -> WebhookActivationResult:
        await AuthorizationService(self.session).require_permission(
            user_id=user_id, tenant_id=tenant_id, permission=Permission.PROJECT_WRITE
        )
        project = await self.session.scalar(
            select(BotProjectRecord)
            .where(BotProjectRecord.id == project_id, BotProjectRecord.tenant_id == tenant_id)
            .with_for_update()
        )
        credential = await self.session.scalar(
            select(BotCredentialRecord)
            .where(BotCredentialRecord.project_id == project_id)
            .with_for_update()
        )
        if project is None or credential is None or project.telegram_bot_id is None:
            raise TelegramWebhookNotReady("Telegram bot provisioning is required first")

        webhook_url = self._webhook_url(project_id)
        state = await self.session.scalar(
            select(TelegramWebhookStateRecord)
            .where(TelegramWebhookStateRecord.project_id == project_id)
            .with_for_update()
        )
        webhook_secret = secrets.token_urlsafe(32)
        credential.webhook_secret_hash = hash_webhook_secret(webhook_secret)
        if state is None:
            state = TelegramWebhookStateRecord(
                project_id=project_id, webhook_url=webhook_url, status="inactive"
            )
            self.session.add(state)
        state.webhook_url = webhook_url
        state.status = "inactive"
        state.last_error = None
        await self.session.flush()

        try:
            async with TelegramBotClientFactory(self.session).bot(project_id) as bot:
                ok = await bot.set_webhook(
                    url=webhook_url,
                    secret_token=webhook_secret,
                    allowed_updates=[],
                    drop_pending_updates=False,
                    max_connections=40,
                )
                if not ok:
                    raise TelegramWebhookError("Telegram did not accept webhook registration")
                info = await bot.get_webhook_info()
                if info.url != webhook_url:
                    raise TelegramWebhookError("Telegram webhook verification failed")
        except Exception as exc:
            state.status = "error"
            state.last_error = "Telegram webhook registration failed"
            await self.session.flush()
            raise TelegramWebhookError("Telegram webhook registration failed") from exc

        state.status = "active"
        state.last_verified_at = datetime.now(UTC)
        state.last_error = None
        await self.session.flush()
        return WebhookActivationResult(project_id, webhook_url, webhook_secret)

    async def deactivate(self, *, user_id: int, tenant_id: UUID, project_id: UUID) -> None:
        await AuthorizationService(self.session).require_permission(
            user_id=user_id, tenant_id=tenant_id, permission=Permission.PROJECT_WRITE
        )
        project = await self.session.scalar(
            select(BotProjectRecord)
            .where(BotProjectRecord.id == project_id, BotProjectRecord.tenant_id == tenant_id)
            .with_for_update()
        )
        if project is None:
            raise TelegramWebhookNotReady("project was not found")
        state = await self.session.scalar(
            select(TelegramWebhookStateRecord)
            .where(TelegramWebhookStateRecord.project_id == project_id)
            .with_for_update()
        )
        if state is None or state.status == "inactive":
            return
        if project.telegram_bot_id is None:
            state.status = "inactive"
            state.last_error = None
            await self.session.flush()
            return

        try:
            async with TelegramBotClientFactory(self.session).bot(project_id) as bot:
                ok = await bot.delete_webhook(drop_pending_updates=False)
                if not ok:
                    raise TelegramWebhookError("Telegram did not accept webhook removal")
                info = await bot.get_webhook_info()
                if info.url:
                    raise TelegramWebhookError("Telegram webhook removal could not be verified")
        except Exception as exc:
            state.status = "error"
            state.last_error = "Telegram webhook removal failed"
            await self.session.flush()
            raise TelegramWebhookError("Telegram webhook removal failed") from exc

        state.status = "inactive"
        state.last_error = None
        state.last_verified_at = datetime.now(UTC)
        await self.session.flush()
