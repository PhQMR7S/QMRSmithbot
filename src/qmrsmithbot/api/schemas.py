from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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
