from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.auth.authorization import AuthorizationService
from qmrsmithbot.auth.models import Principal
from qmrsmithbot.auth.service import (
    AuthenticationError,
    SessionService,
    TenantAccessError,
    TenantSelectionRequired,
    TenantService,
)
from qmrsmithbot.db.models import AuditEvent
from qmrsmithbot.db.session import get_session
from qmrsmithbot.projects.service import ProjectService
from qmrsmithbot.projects.sqlalchemy_store import SQLAlchemyProjectStore

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer session token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return await SessionService(session).authenticate(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_user_id(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> int:
    """Compatibility dependency exposing the authenticated principal's user ID."""
    return principal.user_id


async def get_current_tenant_id(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
    requested_tenant: Annotated[str | None, Header(alias="X-QMRSmith-Tenant-ID")] = None,
) -> UUID:
    tenant_id: UUID | None = None
    if requested_tenant is not None:
        try:
            tenant_id = UUID(requested_tenant)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-QMRSmith-Tenant-ID must be a valid UUID",
            ) from exc
    try:
        tenant = await TenantService(session).resolve_for_user(
            user_id=principal.user_id,
            requested_tenant_id=tenant_id,
        )
    except TenantSelectionRequired as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TenantAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return tenant.id


async def get_authorization_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthorizationService:
    return AuthorizationService(session)


async def get_project_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AsyncIterator[ProjectService]:
    request_id = getattr(request.state, "request_id", None)

    async def audit(action: str, project_id: UUID, actor_user_id: int, tenant_id: UUID) -> None:
        session.add(
            AuditEvent(
                actor_user_id=actor_user_id,
                tenant_id=tenant_id,
                project_id=project_id,
                action=action,
                request_id=request_id,
            )
        )
        await session.flush()

    yield ProjectService(SQLAlchemyProjectStore(session), audit=audit)
