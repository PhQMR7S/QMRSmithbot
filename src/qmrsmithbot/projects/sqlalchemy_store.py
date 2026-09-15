from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.db.models import BotProjectRecord, WorkflowVersionRecord
from qmrsmithbot.domain.models import BotProject as Project
from qmrsmithbot.domain.models import BotStatus, WorkflowVersion
from qmrsmithbot.projects.service import (
    ProjectNotFoundError,
    ProjectStore,
    VersionNotFoundError,
)


class SQLAlchemyProjectStore(ProjectStore):
    """PostgreSQL-backed project store with tenant-scoped queries and row locking."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_project(self, project: Project) -> Project:
        if project.tenant_id is None:
            raise ValueError("tenant id is required")
        record = BotProjectRecord(
            id=project.id,
            owner_id=project.owner_id,
            tenant_id=project.tenant_id,
            name=project.name,
            active_version=project.active_version,
            status=project.status,
        )
        self.session.add(record)
        await self.session.flush()
        return self._project(record)

    async def get_project_for_tenant(self, project_id: UUID, tenant_id: UUID) -> Project | None:
        statement = select(BotProjectRecord).where(
            BotProjectRecord.id == project_id,
            BotProjectRecord.tenant_id == tenant_id,
        )
        record = await self.session.scalar(statement)
        return None if record is None else self._project(record)

    async def create_next_version(
        self, project_id: UUID, definition: dict, version_id: UUID
    ) -> WorkflowVersion:
        project = await self.session.scalar(
            select(BotProjectRecord)
            .where(BotProjectRecord.id == project_id)
            .with_for_update()
        )
        if project is None:
            raise ProjectNotFoundError("project was not found")
        latest = await self.session.scalar(
            select(func.max(WorkflowVersionRecord.version)).where(
                WorkflowVersionRecord.project_id == project_id
            )
        )
        record = WorkflowVersionRecord(
            id=version_id,
            project_id=project_id,
            version=(latest or 0) + 1,
            definition=definition,
        )
        self.session.add(record)
        await self.session.flush()
        return self._version(record)

    async def get_version(self, project_id: UUID, version: int) -> WorkflowVersion | None:
        record = await self.session.scalar(
            select(WorkflowVersionRecord).where(
                WorkflowVersionRecord.project_id == project_id,
                WorkflowVersionRecord.version == version,
            )
        )
        return None if record is None else self._version(record)

    async def list_versions(self, project_id: UUID) -> list[WorkflowVersion]:
        records = await self.session.scalars(
            select(WorkflowVersionRecord)
            .where(WorkflowVersionRecord.project_id == project_id)
            .order_by(WorkflowVersionRecord.version.desc())
        )
        return [self._version(record) for record in records]

    async def activate_version(self, project_id: UUID, version: int) -> Project:
        project = await self.session.scalar(
            select(BotProjectRecord)
            .where(BotProjectRecord.id == project_id)
            .with_for_update()
        )
        if project is None:
            raise ProjectNotFoundError("project was not found")
        version_record = await self.session.scalar(
            select(WorkflowVersionRecord).where(
                WorkflowVersionRecord.project_id == project_id,
                WorkflowVersionRecord.version == version,
            )
        )
        if version_record is None:
            raise VersionNotFoundError(f"workflow version {version} was not found")
        project.active_version = version
        project.status = BotStatus.RUNNING
        if version_record.published_at is None:
            version_record.published_at = datetime.now(UTC)
        await self.session.flush()
        return self._project(project)

    @staticmethod
    def _project(record: BotProjectRecord) -> Project:
        return Project(
            id=record.id,
            owner_id=record.owner_id,
            tenant_id=record.tenant_id,
            name=record.name,
            active_version=record.active_version,
            status=BotStatus(record.status),
        )

    @staticmethod
    def _version(record: WorkflowVersionRecord) -> WorkflowVersion:
        return WorkflowVersion(
            id=record.id,
            project_id=record.project_id,
            version=record.version,
            definition=record.definition,
            published_at=record.published_at,
        )
