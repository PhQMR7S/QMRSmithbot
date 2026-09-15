from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class BotStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class BotProject:
    id: UUID
    owner_id: int
    name: str
    active_version: int | None = None
    status: BotStatus = BotStatus.DRAFT


@dataclass(frozen=True, slots=True)
class PlatformAccessPolicy:
    enabled: bool
    required_channels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkflowVersion:
    id: UUID
    project_id: UUID
    version: int
    definition: dict
    published_at: datetime | None = None
