from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.config import settings
from qmrsmithbot.db.models import AuditEvent
from qmrsmithbot.db.session import get_session
from qmrsmithbot.projects.service import ProjectService
from qmrsmithbot.projects.sqlalchemy_store import SQLAlchemyProjectStore


async def get_current_user_id(
    x_qmrsmith_user_id: Annotated[
        str | None, Header(default=None, alias="X-QMRSmith-User-ID")
    ],
) -> int:
    """Resolve an actor only for non-production development environments.

    Production deliberately fails closed until a real authenticated identity provider is wired.
    """
    if settings.app_env == "production":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authenticated identity provider is not configured",
        )
    if x_qmrsmith_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-QMRSmith-User-ID header is required in development",
        )
    try:
        user_id = int(x_qmrsmith_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-QMRSmith-User-ID must be a positive integer",
        ) from exc
    if user_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-QMRSmith-User-ID must be a positive integer",
        )
    return user_id


async def get_project_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AsyncIterator[ProjectService]:
    async def audit(action: str, project_id: UUID, owner_id: int) -> None:
        session.add(
            AuditEvent(
                actor_user_id=owner_id,
                project_id=project_id,
                action=action,
            )
        )
        await session.flush()

    service = ProjectService(SQLAlchemyProjectStore(session), audit=audit)
    try:
        yield service
    except BaseException:
        await session.rollback()
        raise
    else:
        await session.commit()
