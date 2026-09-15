from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.api.dependencies import get_current_principal, get_current_tenant_id
from qmrsmithbot.api.schemas import TelegramBotProvisionRequest, TelegramBotProvisionResponse
from qmrsmithbot.auth.models import Principal
from qmrsmithbot.db.models import AuditEvent, BotProjectRecord
from qmrsmithbot.db.session import get_session
from qmrsmithbot.request_context import get_request_id
from qmrsmithbot.telegram.provisioning import TelegramBotProvisioningService

router = APIRouter(prefix="/api/v1/projects", tags=["telegram"])


@router.post(
    "/{project_id}/telegram/bot",
    response_model=TelegramBotProvisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def provision_telegram_bot(
    project_id: UUID,
    payload: TelegramBotProvisionRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TelegramBotProvisionResponse:
    provisioned = await TelegramBotProvisioningService(session).provision(
        user_id=principal.user_id,
        tenant_id=tenant_id,
        project_id=project_id,
        raw_bot_token=payload.bot_token,
    )
    session.add(
        AuditEvent(
            actor_user_id=principal.user_id,
            tenant_id=tenant_id,
            project_id=project_id,
            action="telegram.bot.provisioned",
            request_id=get_request_id(),
            metadata_json={
                "telegram_bot_id": provisioned.telegram_bot_id,
                "telegram_username": provisioned.telegram_username,
            },
        )
    )
    await session.flush()
    return TelegramBotProvisionResponse(
        project_id=provisioned.project_id,
        telegram_bot_id=provisioned.telegram_bot_id,
        telegram_username=provisioned.telegram_username,
        webhook_secret=provisioned.webhook_secret,
    )


@router.post(
    "/{project_id}/telegram/webhook-secret/rotate",
    response_model=TelegramBotProvisionResponse,
)
async def rotate_webhook_secret(
    project_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TelegramBotProvisionResponse:
    service = TelegramBotProvisioningService(session)
    secret = await service.rotate_webhook_secret(
        user_id=principal.user_id, tenant_id=tenant_id, project_id=project_id
    )
    project = await session.scalar(
        select(BotProjectRecord).where(
            BotProjectRecord.id == project_id, BotProjectRecord.tenant_id == tenant_id
        )
    )
    if project is None:
        raise RuntimeError("project disappeared during webhook secret rotation")
    session.add(
        AuditEvent(
            actor_user_id=principal.user_id,
            tenant_id=tenant_id,
            project_id=project_id,
            action="telegram.webhook_secret.rotated",
            request_id=get_request_id(),
        )
    )
    await session.flush()
    return TelegramBotProvisionResponse(
        project_id=project_id,
        telegram_bot_id=project.telegram_bot_id,
        telegram_username=project.telegram_username,
        webhook_secret=secret,
    )


@router.delete("/{project_id}/telegram/bot", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_telegram_bot(
    project_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await TelegramBotProvisioningService(session).disconnect(
        user_id=principal.user_id, tenant_id=tenant_id, project_id=project_id
    )
    session.add(
        AuditEvent(
            actor_user_id=principal.user_id,
            tenant_id=tenant_id,
            project_id=project_id,
            action="telegram.bot.disconnected",
            request_id=get_request_id(),
            metadata_json={},
        )
    )
    await session.flush()
