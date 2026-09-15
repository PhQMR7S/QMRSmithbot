from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.auth.models import Principal, Tenant, TenantMembership, TenantRole
from qmrsmithbot.config import settings
from qmrsmithbot.db.models import (
    IdentityRecord,
    SessionRecord,
    TenantMembershipRecord,
    TenantRecord,
    User,
)


class AuthenticationError(Exception):
    """Raised when a session token cannot authenticate an actor."""


class TenantAccessError(Exception):
    """Raised when an actor cannot access or select a tenant."""


class TenantSelectionRequired(TenantAccessError):
    """Raised when a user belongs to multiple tenants and omitted the tenant context."""


class IdentityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_user(self, user_id: int) -> User:
        if user_id <= 0:
            raise ValueError("user id must be positive")
        user = await self.session.get(User, user_id)
        if user is None:
            user = User(id=user_id)
            self.session.add(user)
            await self.session.flush()

        identity = await self.session.scalar(
            select(IdentityRecord).where(
                IdentityRecord.provider == "development",
                IdentityRecord.subject == str(user_id),
            )
        )
        now = datetime.now(UTC)
        if identity is None:
            self.session.add(
                IdentityRecord(
                    user_id=user_id,
                    provider="development",
                    subject=str(user_id),
                    last_authenticated_at=now,
                )
            )
        else:
            identity.last_authenticated_at = now
        await self.session.flush()
        return user


class SessionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(
        self,
        *,
        user_id: int,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[Principal, str, datetime]:
        await self._require_user(user_id)
        raw_token = f"qms_{secrets.token_urlsafe(32)}"
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=settings.session_absolute_ttl_minutes)
        record = SessionRecord(
            id=uuid4(),
            user_id=user_id,
            token_hash=self.hash_token(raw_token),
            expires_at=expires_at,
            last_seen_at=now,
            user_agent=user_agent[:512] if user_agent else None,
            ip_address=ip_address[:64] if ip_address else None,
        )
        self.session.add(record)
        await self.session.flush()
        return Principal(user_id=user_id, session_id=record.id), raw_token, expires_at

    async def authenticate(self, raw_token: str) -> Principal:
        if not raw_token or len(raw_token) > 512:
            raise AuthenticationError("invalid session token")
        now = datetime.now(UTC)
        idle_cutoff = now - timedelta(minutes=settings.session_idle_ttl_minutes)
        token_hash = self.hash_token(raw_token)
        record = await self.session.scalar(
            select(SessionRecord).where(
                SessionRecord.token_hash == token_hash,
                SessionRecord.revoked_at.is_(None),
                SessionRecord.expires_at > now,
                SessionRecord.last_seen_at > idle_cutoff,
            )
        )
        if record is None:
            raise AuthenticationError("invalid or expired session")
        if await self.session.get(User, record.user_id) is None:
            raise AuthenticationError("invalid session owner")
        record.last_seen_at = now
        await self.session.flush()
        return Principal(user_id=record.user_id, session_id=record.id)

    async def revoke(self, session_id: UUID) -> None:
        record = await self.session.get(SessionRecord, session_id)
        if record is not None and record.revoked_at is None:
            record.revoked_at = datetime.now(UTC)
            await self.session.flush()

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    async def _require_user(self, user_id: int) -> User:
        user = await self.session.get(User, user_id)
        if user is None:
            raise AuthenticationError("user does not exist")
        return user


class TenantService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_personal_tenant(self, user_id: int) -> Tenant:
        slug = f"personal-{user_id}"
        membership = await self.session.scalar(
            select(TenantMembershipRecord)
            .join(TenantRecord, TenantRecord.id == TenantMembershipRecord.tenant_id)
            .where(
                TenantMembershipRecord.user_id == user_id,
                TenantMembershipRecord.role == TenantRole.OWNER,
                TenantRecord.slug == slug,
            )
        )
        if membership is not None:
            record = await self.session.get(TenantRecord, membership.tenant_id)
            if record is not None:
                return Tenant(id=record.id, name=record.name, slug=record.slug)

        tenant_id = uuid4()
        try:
            async with self.session.begin_nested():
                tenant = TenantRecord(
                    id=tenant_id,
                    name="Personal workspace",
                    slug=slug,
                    created_by_user_id=user_id,
                )
                self.session.add(tenant)
                await self.session.flush()
                self.session.add(
                    TenantMembershipRecord(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        role=TenantRole.OWNER,
                    )
                )
                await self.session.flush()
        except IntegrityError:
            existing = await self.session.scalar(
                select(TenantRecord).where(TenantRecord.slug == slug)
            )
            if existing is None:
                raise
            membership = await self.session.scalar(
                select(TenantMembershipRecord).where(
                    TenantMembershipRecord.tenant_id == existing.id,
                    TenantMembershipRecord.user_id == user_id,
                )
            )
            if membership is None:
                self.session.add(
                    TenantMembershipRecord(
                        tenant_id=existing.id,
                        user_id=user_id,
                        role=TenantRole.OWNER,
                    )
                )
                await self.session.flush()
            return Tenant(id=existing.id, name=existing.name, slug=existing.slug)

        return Tenant(id=tenant_id, name="Personal workspace", slug=slug)

    async def resolve_for_user(self, *, user_id: int, requested_tenant_id: UUID | None) -> Tenant:
        if requested_tenant_id is not None:
            membership = await self.session.scalar(
                select(TenantMembershipRecord).where(
                    TenantMembershipRecord.tenant_id == requested_tenant_id,
                    TenantMembershipRecord.user_id == user_id,
                )
            )
            if membership is None:
                raise TenantAccessError("tenant is not accessible by the current user")
            record = await self.session.get(TenantRecord, requested_tenant_id)
            if record is None:
                raise TenantAccessError("tenant was not found")
            return Tenant(id=record.id, name=record.name, slug=record.slug)

        memberships = list(
            await self.session.scalars(
                select(TenantMembershipRecord).where(TenantMembershipRecord.user_id == user_id)
            )
        )
        if not memberships:
            return await self.ensure_personal_tenant(user_id)
        if len(memberships) > 1:
            raise TenantSelectionRequired("tenant context is required for this user")
        record = await self.session.get(TenantRecord, memberships[0].tenant_id)
        if record is None:
            raise TenantAccessError("tenant was not found")
        return Tenant(id=record.id, name=record.name, slug=record.slug)

    async def get_membership(self, *, user_id: int, tenant_id: UUID) -> TenantMembership | None:
        record = await self.session.scalar(
            select(TenantMembershipRecord).where(
                TenantMembershipRecord.user_id == user_id,
                TenantMembershipRecord.tenant_id == tenant_id,
            )
        )
        if record is None:
            return None
        return TenantMembership(
            tenant_id=record.tenant_id,
            user_id=record.user_id,
            role=TenantRole(record.role),
        )
