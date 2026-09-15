from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

from qmrsmithbot.domain.models import BotProject as Project
from qmrsmithbot.domain.models import BotStatus
from qmrsmithbot.domain.models import WorkflowVersion
from qmrsmithbot.workflows.schema import WorkflowDefinition


class ProjectNotFoundError(LookupError):
    """Raised when a project does not exist or is not owned by the actor."""


class VersionNotFoundError(LookupError):
    """Raised when a workflow version does not exist for a project."""


class InvalidWorkflowError(ValueError):
    """Raised when a workflow cannot be persisted or published."""


class ProjectStore:
    """Persistence contract for project/version lifecycle operations."""

    async def create_project(self, project: Project) -> Project:
        raise NotImplementedError

    async def get_project_for_owner(self, project_id: UUID, owner_id: int) -> Project | None:
        raise NotImplementedError

    async def create_next_version(
        self, project_id: UUID, definition: dict, version_id: UUID
    ) -> WorkflowVersion:
        """Create the next version atomically with its version allocation."""
        raise NotImplementedError

    async def get_version(self, project_id: UUID, version: int) -> WorkflowVersion | None:
        raise NotImplementedError

    async def activate_version(self, project_id: UUID, version: int) -> Project:
        """Atomically switch the project's active version."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class ProjectService:
    store: ProjectStore
    audit: Callable[[str, UUID, int], Awaitable[None]] | None = None

    async def create_project(self, *, owner_id: int, name: str) -> Project:
        if owner_id <= 0:
            raise ValueError("owner id must be positive")

        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("project name must not be empty")
        if len(normalized_name) > 120:
            raise ValueError("project name must not exceed 120 characters")

        return await self.store.create_project(
            Project(id=uuid4(), owner_id=owner_id, name=normalized_name)
        )

    async def save_version(
        self,
        *,
        project_id: UUID,
        owner_id: int,
        definition: dict,
    ) -> WorkflowVersion:
        self._require_owner(await self.store.get_project_for_owner(project_id, owner_id))
        workflow = self._validate_definition(definition)
        return await self.store.create_next_version(
            project_id,
            workflow.model_dump(mode="json"),
            uuid4(),
        )

    async def publish(
        self,
        *,
        project_id: UUID,
        owner_id: int,
        version: int,
    ) -> Project:
        self._require_owner(await self.store.get_project_for_owner(project_id, owner_id))
        stored = await self.store.get_version(project_id, version)
        if stored is None:
            raise VersionNotFoundError(f"workflow version {version} was not found")
        self._validate_definition(stored.definition)

        project = await self.store.activate_version(project_id, version)
        await self._audit("project.publish", project_id, owner_id)
        return project

    async def rollback(
        self,
        *,
        project_id: UUID,
        owner_id: int,
        version: int,
    ) -> Project:
        self._require_owner(await self.store.get_project_for_owner(project_id, owner_id))
        stored = await self.store.get_version(project_id, version)
        if stored is None:
            raise VersionNotFoundError(f"workflow version {version} was not found")
        self._validate_definition(stored.definition)

        project = await self.store.activate_version(project_id, version)
        await self._audit("project.rollback", project_id, owner_id)
        return project

    async def _audit(self, action: str, project_id: UUID, owner_id: int) -> None:
        if self.audit is not None:
            await self.audit(action, project_id, owner_id)

    @staticmethod
    def _validate_definition(definition: dict) -> WorkflowDefinition:
        try:
            return WorkflowDefinition.model_validate(definition)
        except ValueError as exc:
            raise InvalidWorkflowError(str(exc)) from exc

    @staticmethod
    def _require_owner(project: Project | None) -> Project:
        if project is None:
            raise ProjectNotFoundError("project was not found")
        return project
