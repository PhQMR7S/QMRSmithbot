from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

from qmrsmithbot.domain.models import BotProject as Project
from qmrsmithbot.domain.models import BotStatus, WorkflowVersion
from qmrsmithbot.workflows.schema import WorkflowDefinition


class ProjectNotFoundError(LookupError):
    """Raised when a project does not exist or is outside the tenant scope."""


class VersionNotFoundError(LookupError):
    """Raised when a workflow version does not exist for a project."""


class InvalidWorkflowError(ValueError):
    """Raised when a workflow cannot be persisted or published."""


ProjectAudit = Callable[[str, UUID, int, UUID], Awaitable[None]]


class ProjectStateError(ValueError):
    """A requested lifecycle transition is not safe for the current project."""


class ProjectStore:
    """Persistence contract for tenant-scoped project/version lifecycle operations."""

    async def create_project(self, project: Project) -> Project:
        raise NotImplementedError

    async def list_projects(self, *, tenant_id: UUID, query: str, limit: int,
                            offset: int, status: BotStatus | None) -> list[Project]:
        raise NotImplementedError

    async def rename_project(self, *, project_id: UUID, tenant_id: UUID, name: str) -> Project:
        raise NotImplementedError

    async def set_running(self, *, project_id: UUID, tenant_id: UUID, running: bool) -> Project:
        raise NotImplementedError


    async def get_project_for_tenant(self, project_id: UUID, tenant_id: UUID) -> Project | None:
        raise NotImplementedError

    async def create_next_version(
        self, project_id: UUID, definition: dict, version_id: UUID
    ) -> WorkflowVersion:
        raise NotImplementedError

    async def get_version(self, project_id: UUID, version: int) -> WorkflowVersion | None:
        raise NotImplementedError

    async def list_versions(self, project_id: UUID) -> list[WorkflowVersion]:
        raise NotImplementedError

    async def activate_version(self, project_id: UUID, version: int) -> Project:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class ProjectService:
    store: ProjectStore
    audit: ProjectAudit | None = None

    async def create_project(self, *, owner_id: int, tenant_id: UUID, name: str) -> Project:
        if owner_id <= 0:
            raise ValueError("owner id must be positive")
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("project name must not be empty")
        if len(normalized_name) > 120:
            raise ValueError("project name must not exceed 120 characters")
        return await self.store.create_project(
            Project(id=uuid4(), owner_id=owner_id, tenant_id=tenant_id, name=normalized_name)
        )

    async def list_projects(self, *, tenant_id: UUID, query: str = "", limit: int = 20,
                            offset: int = 0, status: BotStatus | None = None) -> list[Project]:
        if not 1 <= limit <= 101 or offset < 0 or len(query) > 120:
            raise ValueError("Invalid pagination or search")
        return await self.store.list_projects(
            tenant_id=tenant_id, query=query.strip(), limit=limit, offset=offset, status=status
        )

    async def rename(self, *, project_id: UUID, tenant_id: UUID, name: str,
                     actor_user_id: int) -> Project:
        name = name.strip()
        if not name or len(name) > 120:
            raise ValueError("Project name must contain 1 to 120 characters")
        project = await self.store.rename_project(
            project_id=project_id, tenant_id=tenant_id, name=name
        )
        await self._audit("project.rename", project_id, actor_user_id, tenant_id)
        return project

    async def set_running(self, *, project_id: UUID, tenant_id: UUID, running: bool,
                          actor_user_id: int) -> Project:
        project = await self.store.set_running(
            project_id=project_id, tenant_id=tenant_id, running=running
        )
        await self._audit("project.resume" if running else "project.stop",
                          project_id, actor_user_id, tenant_id)
        return project

    async def get_project(self, *, project_id: UUID, tenant_id: UUID) -> Project:
        return self._require_project(await self.store.get_project_for_tenant(project_id, tenant_id))

    async def list_versions(self, *, project_id: UUID, tenant_id: UUID) -> list[WorkflowVersion]:
        await self.get_project(project_id=project_id, tenant_id=tenant_id)
        return await self.store.list_versions(project_id)

    async def save_version(
        self, *, project_id: UUID, tenant_id: UUID, definition: dict
    ) -> WorkflowVersion:
        await self.get_project(project_id=project_id, tenant_id=tenant_id)
        workflow = self._validate_definition(definition)
        return await self.store.create_next_version(
            project_id, workflow.model_dump(mode="json"), uuid4()
        )

    async def publish(
        self,
        *,
        project_id: UUID,
        tenant_id: UUID,
        actor_user_id: int,
        version: int,
    ) -> Project:
        await self.get_project(project_id=project_id, tenant_id=tenant_id)
        stored = self._require_version(await self.store.get_version(project_id, version), version)
        self._validate_definition(stored.definition)
        project = await self.store.activate_version(project_id, version)
        await self._audit("project.publish", project_id, actor_user_id, tenant_id)
        return project

    async def rollback(
        self,
        *,
        project_id: UUID,
        tenant_id: UUID,
        actor_user_id: int,
        version: int,
    ) -> Project:
        await self.get_project(project_id=project_id, tenant_id=tenant_id)
        stored = self._require_version(await self.store.get_version(project_id, version), version)
        self._validate_definition(stored.definition)
        project = await self.store.activate_version(project_id, version)
        await self._audit("project.rollback", project_id, actor_user_id, tenant_id)
        return project

    async def _audit(
        self, action: str, project_id: UUID, actor_user_id: int, tenant_id: UUID
    ) -> None:
        if self.audit is not None:
            await self.audit(action, project_id, actor_user_id, tenant_id)

    @staticmethod
    def _validate_definition(definition: dict) -> WorkflowDefinition:
        try:
            return WorkflowDefinition.model_validate(definition)
        except ValueError as exc:
            raise InvalidWorkflowError(str(exc)) from exc

    @staticmethod
    def _require_project(project: Project | None) -> Project:
        if project is None:
            raise ProjectNotFoundError("project was not found")
        return project

    @staticmethod
    def _require_version(version: WorkflowVersion | None, version_number: int) -> WorkflowVersion:
        if version is None:
            raise VersionNotFoundError(f"workflow version {version_number} was not found")
        return version
