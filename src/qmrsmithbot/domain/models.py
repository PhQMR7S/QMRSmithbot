from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class BotStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class BotProject:
    id: str
    owner_id: int
    name: str
    telegram_username: str | None
    status: BotStatus
    active_version: int | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PlatformAccessPolicy:
    enabled: bool
    required_channels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkflowVersion:
    project_id: str
    version: int
    definition: dict
    published_at: datetime | None
