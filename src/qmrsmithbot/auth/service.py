from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.auth.models import (
    ROLE_RANK,
    Principal,
    Tenant,
    TenantMember,
    TenantMembership,
    TenantRole,
)
from qmrsmithbot.config import settings
from qmrsmithbot.db.models import (
    IdentityRecord,
    SessionRecord,
    TenantInvitationRecord,
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


class TenantAdministrationError(Exception):
    """Raised when a tenant administration operation violates a business invariant."""


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

    async def revoke_all(self, *, user_id: int) -> int:
        result = await self.session.execute(
            select(SessionRecord).where(
                SessionRecord.user_id == user_id,
                SessionRecord.revoked_at.is_(None),
            )
        )
        records = list(result.scalars())
        now = datetime.now(UTC)
        for record in records:
            record.revoked_at = now
        await self.session.flush()
        return len(records)

    async def revoke_all_except(self, *, user_id: int, session_id: UUID) -> int:
        result = await self.session.execute(
            select(SessionRecord).where(
                SessionRecord.user_id == user_id,
                SessionRecord.id != session_id,
                SessionRecord.revoked_at.is_(None),
            )
        )
        records = list(result.scalars())
        now = datetime.now(UTC)
        for record in records:
            record.revoked_at = now
        await self.session.flush()
        return len(records)

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    async def _require_user(self, user_id: int) -> User:
        user = await self.session.get(User, user_id)
        if user is None:
            raise AuthenticationError("user does not exist")
        return user


class TenantService:
    _slug_pattern = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,118}[a-z0-9])?$")

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def normalize_email(email: str) -> str:
        normalized = email.strip().casefold()
        if len(normalized) > 320 or "@" not in normalized:
            raise TenantAdministrationError("invalid email address")
        return normalized

    @classmethod
    def normalize_slug(cls, slug: str) -> str:
        normalized = slug.strip().lower()
        if not cls._slug_pattern.fullmatch(normalized):
            raise TenantAdministrationError(
                "tenant slug must contain only lowercase letters, digits, and hyphens"
            )
        return normalized

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
            existing = await self.session.scalar(select(TenantRecord).where(TenantRecord.slug == slug))
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

    async def list_tenants(self, user_id: int) -> list[Tenant]:
        rows = await self.session.execute(
            select(TenantRecord)
            .join(TenantMembershipRecord, TenantMembershipRecord.tenant_id == TenantRecord.id)
            .where(TenantMembershipRecord.user_id == user_id)
            .order_by(TenantRecord.name)
        )
        return [Tenant(id=row.id, name=row.name, slug=row.slug) for row in rows.scalars()]

    async def create_tenant(self, *, user_id: int, name: str, slug: str) -> Tenant:
        normalized_name = name.strip()
        normalized_slug = self.normalize_slug(slug)
        if not normalized_name or len(normalized_name) > 120:
            raise TenantAdministrationError("tenant name must contain 1-120 characters")
        tenant = TenantRecord(
            id=uuid4(), name=normalized_name, slug=normalized_slug, created_by_user_id=user_id
        )
        self.session.add(tenant)
        try:
            await self.session.flush()
            self.session.add(
                TenantMembershipRecord(tenant_id=tenant.id, user_id=user_id, role=TenantRole.OWNER)
            )
            await self.session.flush()
        except IntegrityError as exc:
            raise TenantAdministrationError("tenant slug is already in use") from exc
        return Tenant(id=tenant.id, name=tenant.name, slug=tenant.slug)

    async def list_members(self, tenant_id: UUID) -> list[TenantMember]:
        rows = await self.session.execute(
            select(TenantMembershipRecord, User, IdentityRecord)
            .join(User, User.id == TenantMembershipRecord.user_id)
            .outerjoin(
                IdentityRecord,
                (IdentityRecord.user_id == User.id) & IdentityRecord.email_verified.is_(True),
            )
            .where(TenantMembershipRecord.tenant_id == tenant_id)
            .order_by(TenantMembershipRecord.created_at)
        )
        members: dict[int, TenantMember] = {}
        for membership, user, identity in rows:
            if membership.user_id not in members:
                members[membership.user_id] = TenantMember(
                    tenant_id=tenant_id,
                    user_id=user.id,
                    role=TenantRole(membership.role),
                    username=user.username,
                    email=identity.email if identity else None,
                )
        return list(members.values())

    async def create_invitation(
        self, *, tenant_id: UUID, invited_by_user_id: int, email: str, role: TenantRole
    ) -> tuple[UUID, str, datetime]:
        if role == TenantRole.OWNER:
            raise TenantAdministrationError("owner cannot be assigned through an invitation")
        normalized_email = self.normalize_email(email)
        existing_member = await self.session.scalar(
            select(TenantMembershipRecord)
            .join(IdentityRecord, IdentityRecord.user_id == TenantMembershipRecord.user_id)
            .where(
                TenantMembershipRecord.tenant_id == tenant_id,
                IdentityRecord.email == normalized_email,
                IdentityRecord.email_verified.is_(True),
            )
        )
        if existing_member is not None:
            raise TenantAdministrationError("user is already a tenant member")
        active = await self.session.scalar(
            select(TenantInvitationRecord).where(
                TenantInvitationRecord.tenant_id == tenant_id,
                TenantInvitationRecord.email == normalized_email,
                TenantInvitationRecord.accepted_at.is_(None),
                TenantInvitationRecord.revoked_at.is_(None),
            )
        )
        if active is not None:
            raise TenantAdministrationError("an active invitation already exists")
        raw_token = f"qmi_{secrets.token_urlsafe(32)}"
        expires_at = datetime.now(UTC) + timedelta(days=7)
        record = TenantInvitationRecord(
            id=uuid4(),
            tenant_id=tenant_id,
            invited_by_user_id=invited_by_user_id,
            email=normalized_email,
            role=role.value,
            token_hash=SessionService.hash_token(raw_token),
            expires_at=expires_at,
        )
        self.session.add(record)
        await self.session.flush()
        return record.id, raw_token, expires_at

    async def revoke_invitation(self, *, tenant_id: UUID, invitation_id: UUID) -> None:
        record = await self.session.scalar(
            select(TenantInvitationRecord).where(
                TenantInvitationRecord.id == invitation_id,
                TenantInvitationRecord.tenant_id == tenant_id,
                TenantInvitationRecord.accepted_at.is_(None),
                TenantInvitationRecord.revoked_at.is_(None),
            )
        )
        if record is None:
            raise TenantAdministrationError("invitation was not found or is no longer active")
        record.revoked_at = datetime.now(UTC)
        await self.session.flush()

    async def accept_invitation(self, *, user_id: int, raw_token: str) -> UUID:
        record = await self.session.scalar(
            select(TenantInvitationRecord).where(
                TenantInvitationRecord.token_hash == SessionService.hash_token(raw_token),
                TenantInvitationRecord.accepted_at.is_(None),
                TenantInvitationRecord.revoked_at.is_(None),
                TenantInvitationRecord.expires_at > datetime.now(UTC),
            )
        )
        if record is None:
            raise TenantAdministrationError("invitation is invalid or expired")
        verified_users = list(
            await self.session.scalars(
                select(IdentityRecord.user_id)
                .where(
                    IdentityRecord.email == record.email,
                    IdentityRecord.email_verified.is_(True),
                )
                .distinct()
            )
        )
        if len(set(verified_users)) != 1 or verified_users[0] != user_id:
            raise TenantAdministrationError("invitation email does not match the authenticated identity")
        membership = await self.session.get(
            TenantMembershipRecord, {"tenant_id": record.tenant_id, "user_id": user_id}
        )
        if membership is None:
            self.session.add(
                TenantMembershipRecord(
                    tenant_id=record.tenant_id, user_id=user_id, role=record.role
                )
            )
        record.accepted_at = datetime.now(UTC)
        await self.session.flush()
        return record.tenant_id

    async def change_role(
        self, *, tenant_id: UUID, target_user_id: int, new_role: TenantRole, actor_role: TenantRole
    ) -> None:
        membership = await self.session.get(
            TenantMembershipRecord, {"tenant_id": tenant_id, "user_id": target_user_id}
        )
        if membership is None:
            raise TenantAdministrationError("member was not found")
        current_role = TenantRole(membership.role)
        if new_role == current_role:
            return
        if new_role == TenantRole.OWNER:
            raise TenantAdministrationError(
                "owner transfer must use the dedicated ownership transfer operation"
            )
        if ROLE_RANK[actor_role] <= ROLE_RANK[current_role]:
            raise TenantAdministrationError("actor cannot change an equal or higher privilege role")
        if ROLE_RANK[actor_role] <= ROLE_RANK[new_role]:
            raise TenantAdministrationError("actor cannot grant an equal or higher privilege role")
        if current_role == TenantRole.OWNER:
            raise TenantAdministrationError("owner role cannot be changed here")
        membership.role = new_role.value
        await self.session.flush()

    async def transfer_ownership(self, *, tenant_id: UUID, current_owner_id: int, new_owner_id: int) -> None:
        if current_owner_id == new_owner_id:
            raise TenantAdministrationError("new owner must be a different member")
        current = await self.session.get(
            TenantMembershipRecord, {"tenant_id": tenant_id, "user_id": current_owner_id}
        )
        target = await self.session.get(
            TenantMembershipRecord, {"tenant_id": tenant_id, "user_id": new_owner_id}
        )
        if current is None or TenantRole(current.role) != TenantRole.OWNER:
            raise TenantAdministrationError("current actor is not the tenant owner")
        if target is None:
            raise TenantAdministrationError("new owner must already be a tenant member")
        current.role = TenantRole.ADMIN.value
        target.role = TenantRole.OWNER.value
        await self.session.flush()

    async def remove_member(self, *, tenant_id: UUID, target_user_id: int, actor_role: TenantRole) -> None:
        membership = await self.session.get(
            TenantMembershipRecord, {"tenant_id": tenant_id, "user_id": target_user_id}
        )
        if membership is None:
            raise TenantAdministrationError("member was not found")
        target_role = TenantRole(membership.role)
        if target_role == TenantRole.OWNER:
            raise TenantAdministrationError("owner must transfer ownership before removal")
        if ROLE_RANK[actor_role] <= ROLE_RANK[target_role]:
            raise TenantAdministrationError("actor cannot remove an equal or higher privilege member")
        await self.session.delete(membership)
        await self.session.flush()

    async def owner_count(self, tenant_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(TenantMembershipRecord)
                .where(
                    TenantMembershipRecord.tenant_id == tenant_id,
                    TenantMembershipRecord.role == TenantRole.OWNER,
                )
            )
            or 0
        )
