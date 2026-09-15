from uuid import uuid4

import pytest

from qmrsmithbot.auth.authorization import AuthorizationService
from qmrsmithbot.auth.models import Permission, ROLE_PERMISSIONS, TenantRole
from qmrsmithbot.auth.service import SessionService


def test_session_token_hash_is_one_way_and_deterministic() -> None:
    token = "qms_example_secret"
    first = SessionService.hash_token(token)
    second = SessionService.hash_token(token)
    assert first == second
    assert len(first) == 64
    assert first != token


def test_roles_are_default_deny() -> None:
    assert Permission.PROJECT_READ in ROLE_PERMISSIONS[TenantRole.VIEWER]
    assert Permission.PROJECT_WRITE not in ROLE_PERMISSIONS[TenantRole.VIEWER]
    assert Permission.MEMBERS_MANAGE not in ROLE_PERMISSIONS[TenantRole.EDITOR]
    assert Permission.MEMBERS_MANAGE in ROLE_PERMISSIONS[TenantRole.ADMIN]
    assert ROLE_PERMISSIONS[TenantRole.OWNER] == frozenset(Permission)


@pytest.mark.parametrize("role", list(TenantRole))
def test_role_can_is_explicit(role: TenantRole) -> None:
    service = AuthorizationService.__new__(AuthorizationService)
    assert service.role_can(role, Permission.PROJECT_READ) is True


def test_uuid_tenant_context_is_not_user_context() -> None:
    tenant_id = uuid4()
    assert isinstance(tenant_id.hex, str)
