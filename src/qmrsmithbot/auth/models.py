from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class TenantRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class Permission(StrEnum):
    PROJECT_READ = "project.read"
    PROJECT_WRITE = "project.write"
    PROJECT_PUBLISH = "project.publish"
    TENANT_READ = "tenant.read"
    TENANT_MANAGE = "tenant.manage"
    MEMBERS_READ = "members.read"
    MEMBERS_MANAGE = "members.manage"
    INVITATIONS_MANAGE = "invitations.manage"


ROLE_PERMISSIONS: dict[TenantRole, frozenset[Permission]] = {
    TenantRole.OWNER: frozenset(Permission),
    TenantRole.ADMIN: frozenset(
        {
            Permission.PROJECT_READ,
            Permission.PROJECT_WRITE,
            Permission.PROJECT_PUBLISH,
            Permission.TENANT_READ,
            Permission.TENANT_MANAGE,
            Permission.MEMBERS_READ,
            Permission.MEMBERS_MANAGE,
            Permission.INVITATIONS_MANAGE,
        }
    ),
    TenantRole.EDITOR: frozenset(
        {
            Permission.PROJECT_READ,
            Permission.PROJECT_WRITE,
            Permission.PROJECT_PUBLISH,
            Permission.TENANT_READ,
        }
    ),
    TenantRole.VIEWER: frozenset({Permission.PROJECT_READ, Permission.TENANT_READ}),
}

ROLE_RANK: dict[TenantRole, int] = {
    TenantRole.VIEWER: 10,
    TenantRole.EDITOR: 20,
    TenantRole.ADMIN: 30,
    TenantRole.OWNER: 40,
}


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: int
    session_id: UUID


@dataclass(frozen=True, slots=True)
class TenantMembership:
    tenant_id: UUID
    user_id: int
    role: TenantRole


@dataclass(frozen=True, slots=True)
class Tenant:
    id: UUID
    name: str
    slug: str


@dataclass(frozen=True, slots=True)
class TenantMember:
    tenant_id: UUID
    user_id: int
    role: TenantRole
    username: str | None
    email: str | None


@dataclass(frozen=True, slots=True)
class Invitation:
    id: UUID
    tenant_id: UUID
    email: str
    role: TenantRole
    expires_at: object
