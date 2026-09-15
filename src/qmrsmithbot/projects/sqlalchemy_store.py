from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.db.models import BotProjectRecord, WorkflowVersionRecord
from qmrsmithbot.projects.service import Project, ProjectStore, WorkflowVersion


class SQLAlchemyProjectStore(ProjectStore):
    """PostgreSQL-backed project store with row-locked version allocation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_project(self, project: Project) -> Project:
        record = BotProjectRecord(
            id=project.id,
            owner_id=project.owner_id,
            name=project.name,
            active_version=project.active_version,
            status=project.status,
        )
        self.session.add(record)
        await self.session.flush()
        return self._project(record)

    async def get_project_for_owner(self, project_id: UUID, owner_id: int) -> Project | None:
        statement = select(BotProjectRecord).where(
            BotProjectRecord.id == project_id,
            BotProjectRecord.owner_id == owner_id,
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
            raise LookupError("project was not found")

        latest = await self.session.scalar(
            select(func.max(WorkflowVersionRecord.version)).where(
                WorkflowVersionRecord.project_id == project_id
            )
        )
        next_version = (latest or 0) + 1
        record = WorkflowVersionRecord(
            id=version_id,
            project_id=project_id,
            version=next_version,
            definition=definition,
        )
        self.session.add(record)
        await self.session.flush()
        return self._version(record)

    async def get_version(self, project_id: UUID, version: int) -> WorkflowVersion | None:
        statement = select(WorkflowVersionRecord).where(
            WorkflowVersionRecord.project_id == project_id,
            WorkflowVersionRecord.version == version,
        )
        record = await self.session.scalar(statement)
        return None if record is None else self._version(record)

    async def activate_version(self, project_id: UUID, version: int) -> Project:
        project = await self.session.scalar(
            select(BotProjectRecord)
            .where(BotProjectRecord.id == project_id)
            .with_for_update()
        )
        if project is None:
            raise LookupError("project was not found")

        version_record = await self.session.scalar(
            select(WorkflowVersionRecord).where(
                WorkflowVersionRecord.project_id == project_id,
                WorkflowVersionRecord.version == version,
            )
        )
        if version_record is None:
            raise LookupError(f"workflow version {version} was not found")

        await self.session.execute(
            update(BotProjectRecord)
            .where(BotProjectRecord.id == project_id)
            .values(active_version=version, status="running")
        )
        if version_record.published_at is None:
            version_record.published_at = datetime.now(timezone.utc)
        await self.session.flush()
        project.active_version = version
        project.status = "running"
        return self._project(project)

    @staticmethod
    def _project(record: BotProjectRecord) -> Project:
        return Project(
            id=record.id,
            owner_id=record.owner_id,
            name=record.name,
            active_version=record.active_version,
            status=record.status,
        )

    @staticmethod
    def _version(record: WorkflowVersionRecord) -> WorkflowVersion:
        return WorkflowVersion(
            id=record.id,
            project_id=record.project_id,
            version=record.version,
            definition=record.definition,
            published=record.published_at is not None,
        )
