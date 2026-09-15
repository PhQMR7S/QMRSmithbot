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
    TENANT_MANAGE = "tenant.manage"
    MEMBERS_MANAGE = "members.manage"


ROLE_PERMISSIONS: dict[TenantRole, frozenset[Permission]] = {
    TenantRole.OWNER: frozenset(Permission),
    TenantRole.ADMIN: frozenset(
        {
            Permission.PROJECT_READ,
            Permission.PROJECT_WRITE,
            Permission.PROJECT_PUBLISH,
            Permission.TENANT_MANAGE,
            Permission.MEMBERS_MANAGE,
        }
    ),
    TenantRole.EDITOR: frozenset(
        {
            Permission.PROJECT_READ,
            Permission.PROJECT_WRITE,
            Permission.PROJECT_PUBLISH,
        }
    ),
    TenantRole.VIEWER: frozenset({Permission.PROJECT_READ}),
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
