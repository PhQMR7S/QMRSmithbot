from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.api.dependencies import get_current_principal
from qmrsmithbot.api.schemas import DevSessionRequest, SessionResponse, SessionUserResponse
from qmrsmithbot.auth.models import Principal
from qmrsmithbot.auth.service import IdentityService, SessionService, TenantService
from qmrsmithbot.config import settings
from qmrsmithbot.db.session import get_session
from qmrsmithbot.rate_limit import enforce_auth_rate_limit

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
RateLimitDependency = Annotated[None, Depends(enforce_auth_rate_limit)]


@router.post("/dev/session", response_model=SessionResponse)
async def create_development_session(
    payload: DevSessionRequest,
    _: RateLimitDependency,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    user_agent: Annotated[str | None, Header(alias="User-Agent")] = None,
) -> SessionResponse:
    if settings.app_env == "production" or not settings.auth_dev_bootstrap_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="endpoint not available")
    await IdentityService(session).ensure_user(payload.user_id)
    await TenantService(session).ensure_personal_tenant(payload.user_id)
    client_ip = request.client.host if request.client is not None else None
    principal, token, expires_at = await SessionService(session).create_session(
        user_id=payload.user_id,
        user_agent=user_agent,
        ip_address=client_ip,
    )
    return SessionResponse(
        access_token=token,
        token_type="bearer",
        expires_at=expires_at,
        session_id=principal.session_id,
    )


@router.get("/me", response_model=SessionUserResponse)
async def get_current_session(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> SessionUserResponse:
    return SessionUserResponse(user_id=principal.user_id, session_id=principal.session_id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await SessionService(session).revoke(principal.session_id)
