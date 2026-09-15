import pytest

from qmrsmithbot.auth.models import ROLE_PERMISSIONS, ROLE_RANK, Permission, TenantRole
from qmrsmithbot.auth.service import TenantAdministrationError, TenantService


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" User@Example.COM ", "user@example.com"),
        ("ADMIN@EXAMPLE.ORG", "admin@example.org"),
    ],
)
def test_email_normalization_is_deterministic(raw: str, expected: str) -> None:
    assert TenantService.normalize_email(raw) == expected


@pytest.mark.parametrize("slug", ["bad slug", "bad_slug", "-leading", "trailing-"])
def test_tenant_slug_rejects_unsafe_values(slug: str) -> None:
    with pytest.raises(TenantAdministrationError):
        TenantService.normalize_slug(slug)


def test_tenant_slug_is_normalized() -> None:
    assert TenantService.normalize_slug("Acme-42") == "acme-42"


def test_privilege_order_is_strict() -> None:
    assert ROLE_RANK[TenantRole.OWNER] > ROLE_RANK[TenantRole.ADMIN]
    assert ROLE_RANK[TenantRole.ADMIN] > ROLE_RANK[TenantRole.EDITOR]
    assert ROLE_RANK[TenantRole.EDITOR] > ROLE_RANK[TenantRole.VIEWER]


def test_viewer_cannot_manage_members_or_invitations() -> None:
    permissions = ROLE_PERMISSIONS[TenantRole.VIEWER]
    assert Permission.MEMBERS_MANAGE not in permissions
    assert Permission.INVITATIONS_MANAGE not in permissions


def test_editor_cannot_manage_tenant_membership() -> None:
    permissions = ROLE_PERMISSIONS[TenantRole.EDITOR]
    assert Permission.TENANT_MANAGE not in permissions
    assert Permission.MEMBERS_READ not in permissions


def test_admin_can_manage_members_but_not_owner() -> None:
    permissions = ROLE_PERMISSIONS[TenantRole.ADMIN]
    assert Permission.MEMBERS_MANAGE in permissions
    assert ROLE_RANK[TenantRole.ADMIN] < ROLE_RANK[TenantRole.OWNER]
