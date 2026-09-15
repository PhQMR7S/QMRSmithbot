from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from qmrsmithbot.auth.models import TenantRole
from qmrsmithbot.domain.models import BotStatus


class DevSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int = Field(gt=0)


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str
    expires_at: datetime
    session_id: UUID


class SessionUserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    session_id: UUID


class OIDCStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorization_url: str


class OIDCCallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=4096)
    state: str = Field(min_length=1, max_length=512)


class TenantCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=120)


class TenantResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    slug: str


class TenantMemberResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    user_id: int
    role: TenantRole
    username: str | None
    email: str | None


class MemberRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: TenantRole


class TenantInvitationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    role: TenantRole = TenantRole.VIEWER


class TenantInvitationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitation_id: UUID
    expires_at: datetime
    invitation_token: str


class TenantInvitationAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitation_token: str = Field(min_length=1, max_length=512)


class OwnershipTransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_owner_user_id: int = Field(gt=0)


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    owner_id: int
    tenant_id: UUID
    name: str
    active_version: int | None
    status: BotStatus


class WorkflowVersionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: dict[str, Any]


class WorkflowVersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    project_id: UUID
    version: int
    definition: dict[str, Any]
    published_at: datetime | None
