from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from qmrsmithbot.domain.models import BotStatus


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    owner_id: int
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
