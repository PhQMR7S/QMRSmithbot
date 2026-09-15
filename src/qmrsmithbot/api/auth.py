from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.api.dependencies import get_current_principal
from qmrsmithbot.api.schemas import (
    DevSessionRequest,
    OIDCCallbackRequest,
    OIDCStartResponse,
    SessionResponse,
    SessionUserResponse,
)
from qmrsmithbot.auth.models import Principal
from qmrsmithbot.auth.oidc import IdentityAlreadyLinked, OIDCError, OIDCService
from qmrsmithbot.auth.service import IdentityService, SessionService, TenantService
from qmrsmithbot.config import settings
from qmrsmithbot.db.models import AuditEvent
from qmrsmithbot.db.session import get_session
from qmrsmithbot.rate_limit import enforce_auth_rate_limit
from qmrsmithbot.request_context import get_request_id

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
    session.add(
        AuditEvent(
            actor_user_id=payload.user_id,
            action="auth.dev_session.created",
            request_id=get_request_id(),
            metadata_json={"session_id": str(principal.session_id)},
        )
    )
    await session.flush()
    return SessionResponse(
        access_token=token,
        token_type="bearer",
        expires_at=expires_at,
        session_id=principal.session_id,
    )


@router.get("/oidc/start", response_model=OIDCStartResponse)
async def start_oidc_login(
    _: RateLimitDependency,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OIDCStartResponse:
    service = OIDCService(session)
    try:
        return OIDCStartResponse(authorization_url=await service.begin())
    except OIDCError as exc:
        raise HTTPException(status_code=503, detail="OIDC provider is unavailable") from exc
    finally:
        await service.close()


@router.get("/oidc/link/start", response_model=OIDCStartResponse)
async def start_oidc_link(
    _: RateLimitDependency,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OIDCStartResponse:
    service = OIDCService(session)
    try:
        return OIDCStartResponse(authorization_url=await service.begin(user_id=principal.user_id))
    except OIDCError as exc:
        raise HTTPException(status_code=503, detail="OIDC provider is unavailable") from exc
    finally:
        await service.close()


async def _finish_oidc_callback(
    *, code: str, state: str, session: AsyncSession
) -> SessionResponse:
    service = OIDCService(session)
    try:
        principal, token, expires_at = await service.callback(code=code, state=state)
    except IdentityAlreadyLinked as exc:
        session.add(
            AuditEvent(
                action="auth.oidc.identity_link_denied",
                request_id=get_request_id(),
                detail="external identity is already linked",
            )
        )
        await session.flush()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OIDCError as exc:
        session.add(
            AuditEvent(
                action="auth.oidc.login_failed",
                request_id=get_request_id(),
                detail="OIDC authentication transaction failed",
            )
        )
        await session.flush()
        raise HTTPException(status_code=401, detail="OIDC authentication failed") from exc
    finally:
        await service.close()
    session.add(
        AuditEvent(
            actor_user_id=principal.user_id,
            action="auth.oidc.login_succeeded",
            request_id=get_request_id(),
            metadata_json={"session_id": str(principal.session_id)},
        )
    )
    await session.flush()
    return SessionResponse(
        access_token=token,
        token_type="bearer",
        expires_at=expires_at,
        session_id=principal.session_id,
    )


@router.get("/oidc/callback", response_model=SessionResponse)
async def oidc_callback(
    code: str,
    state: str,
    _: RateLimitDependency,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SessionResponse:
    return await _finish_oidc_callback(code=code, state=state, session=session)


@router.post("/oidc/callback", response_model=SessionResponse)
async def oidc_callback_post(
    payload: OIDCCallbackRequest,
    _: RateLimitDependency,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SessionResponse:
    return await _finish_oidc_callback(code=payload.code, state=payload.state, session=session)


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
    session.add(
        AuditEvent(
            actor_user_id=principal.user_id,
            action="auth.session.revoked",
            request_id=get_request_id(),
            metadata_json={"session_id": str(principal.session_id)},
        )
    )
    await session.flush()
