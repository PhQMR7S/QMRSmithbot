"""Ensure generated bot webhooks fail closed without a verified consumer."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from qmrsmithbot.telegram.webhook_service import (
    TelegramWebhookNotReady,
    TelegramWebhookService,
)


@pytest.mark.asyncio
async def test_webhook_activation_requires_verified_runtime(monkeypatch):
    from qmrsmithbot.telegram import webhook_service as module

    tenant_id = uuid4()
    project_id = uuid4()
    session = AsyncMock()
    # The project must contain a Telegram ID to pass provisioning checks.
    class Project:
        telegram_bot_id = 42

    session.scalar.side_effect = [Project(), object()]
    monkeypatch.setattr(module.settings, "telegram_runtime_consumer_verified", False)
    monkeypatch.setattr(
        module.AuthorizationService,
        "require_permission",
        AsyncMock(),
    )
    with pytest.raises(TelegramWebhookNotReady, match="consumer has not been verified"):
        await TelegramWebhookService(session).activate(
            user_id=1, tenant_id=tenant_id, project_id=project_id
        )
    assert session.scalar.await_count == 2
