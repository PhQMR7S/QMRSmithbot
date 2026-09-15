from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.auth.models import ROLE_PERMISSIONS, Permission, TenantMembership, TenantRole
from qmrsmithbot.auth.service import TenantService
from qmrsmithbot.db.models import AuditEvent
from qmrsmithbot.request_context import get_request_id


class AuthorizationDenied(PermissionError):
    """Raised when an authenticated actor lacks a required permission."""


class AuthorizationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tenants = TenantService(session)

    async def _deny(self, *, user_id: int, tenant_id: UUID, detail: str) -> None:
        self.session.add(
            AuditEvent(
                actor_user_id=user_id,
                tenant_id=tenant_id,
                action="authorization.denied",
                detail=detail,
                request_id=get_request_id(),
            )
        )
        await self.session.flush()
        raise AuthorizationDenied(detail)

    async def membership(self, *, user_id: int, tenant_id: UUID) -> TenantMembership:
        membership = await self.tenants.get_membership(user_id=user_id, tenant_id=tenant_id)
        if membership is None:
            await self._deny(
                user_id=user_id,
                tenant_id=tenant_id,
                detail="tenant membership is required",
            )
        return membership

    async def require_permission(
        self, *, user_id: int, tenant_id: UUID, permission: Permission
    ) -> TenantMembership:
        membership = await self.membership(user_id=user_id, tenant_id=tenant_id)
        if permission not in ROLE_PERMISSIONS[membership.role]:
            await self._deny(
                user_id=user_id,
                tenant_id=tenant_id,
                detail=f"role '{membership.role}' does not grant '{permission}'",
            )
        return membership

    @staticmethod
    def role_can(role: TenantRole, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS[role]
