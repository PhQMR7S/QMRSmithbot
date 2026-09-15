from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from qmrsmithbot.domain.models import BotProject as Project
from qmrsmithbot.domain.models import WorkflowVersion
from qmrsmithbot.projects.service import (
    InvalidWorkflowError,
    ProjectNotFoundError,
    ProjectService,
    VersionNotFoundError,
)

VALID_WORKFLOW = {
    "nodes": [
        {"id": "start", "type": "trigger.command"},
        {"id": "reply", "type": "action.message"},
    ],
    "edges": [{"source": "start", "target": "reply"}],
}
TENANT_A = uuid4()
TENANT_B = uuid4()


class FakeProjectStore:
    def __init__(self) -> None:
        self.projects: dict[UUID, Project] = {}
        self.versions: dict[tuple[UUID, int], WorkflowVersion] = {}

    async def create_project(self, project: Project) -> Project:
        self.projects[project.id] = project
        return project

    async def get_project_for_tenant(self, project_id: UUID, tenant_id: UUID) -> Project | None:
        project = self.projects.get(project_id)
        return project if project is not None and project.tenant_id == tenant_id else None

    async def create_next_version(
        self, project_id: UUID, definition: dict, version_id: UUID
    ) -> WorkflowVersion:
        versions = [version for (pid, _), version in self.versions.items() if pid == project_id]
        next_version = max((version.version for version in versions), default=0) + 1
        created = WorkflowVersion(version_id, project_id, next_version, definition)
        self.versions[(project_id, next_version)] = created
        return created

    async def get_version(self, project_id: UUID, version: int) -> WorkflowVersion | None:
        return self.versions.get((project_id, version))

    async def list_versions(self, project_id: UUID) -> list[WorkflowVersion]:
        return sorted(
            (version for (pid, _), version in self.versions.items() if pid == project_id),
            key=lambda version: version.version,
            reverse=True,
        )

    async def activate_version(self, project_id: UUID, version: int) -> Project:
        project = self.projects[project_id]
        updated = Project(
            project.id,
            project.owner_id,
            project.name,
            project.tenant_id,
            version,
            project.status,
        )
        self.projects[project_id] = updated
        stored = self.versions[(project_id, version)]
        if stored.published_at is None:
            self.versions[(project_id, version)] = WorkflowVersion(
                stored.id,
                stored.project_id,
                stored.version,
                stored.definition,
                datetime.now(UTC),
            )
        return updated


async def test_create_project_normalizes_name() -> None:
    store = FakeProjectStore()
    service = ProjectService(store)
    project = await service.create_project(owner_id=42, tenant_id=TENANT_A, name="  My Bot  ")
    assert project.name == "My Bot"
    assert project.owner_id == 42
    assert project.tenant_id == TENANT_A


@pytest.mark.parametrize("name", ["", "   "])
async def test_create_project_rejects_empty_name(name: str) -> None:
    service = ProjectService(FakeProjectStore())
    with pytest.raises(ValueError, match="must not be empty"):
        await service.create_project(owner_id=42, tenant_id=TENANT_A, name=name)


async def test_create_project_rejects_non_positive_owner() -> None:
    service = ProjectService(FakeProjectStore())
    with pytest.raises(ValueError, match="owner id must be positive"):
        await service.create_project(owner_id=0, tenant_id=TENANT_A, name="My Bot")


async def test_tenant_scope_blocks_cross_tenant_access() -> None:
    store = FakeProjectStore()
    project = Project(uuid4(), 42, "My Bot", TENANT_A)
    await store.create_project(project)
    service = ProjectService(store)
    assert await service.get_project(project_id=project.id, tenant_id=TENANT_A) == project
    with pytest.raises(ProjectNotFoundError):
        await service.get_project(project_id=project.id, tenant_id=TENANT_B)


async def test_save_version_is_tenant_scoped_and_validated() -> None:
    store = FakeProjectStore()
    project = Project(uuid4(), 42, "My Bot", TENANT_A)
    await store.create_project(project)
    service = ProjectService(store)
    version = await service.save_version(
        project_id=project.id, tenant_id=TENANT_A, definition=VALID_WORKFLOW
    )
    assert version.version == 1
    assert version.definition["schema_version"] == 1
    with pytest.raises(ProjectNotFoundError):
        await service.save_version(project_id=project.id, tenant_id=TENANT_B, definition=VALID_WORKFLOW)
    with pytest.raises(InvalidWorkflowError, match="trigger"):
        await service.save_version(
            project_id=project.id,
            tenant_id=TENANT_A,
            definition={"nodes": [{"id": "reply", "type": "action.message"}]},
        )


async def test_publish_and_rollback_are_audited() -> None:
    store = FakeProjectStore()
    project = Project(uuid4(), 42, "My Bot", TENANT_A)
    await store.create_project(project)
    events: list[str] = []

    async def audit(action: str, project_id: UUID, owner_id: int) -> None:
        events.append(f"{action}:{project_id}:{owner_id}")

    service = ProjectService(store, audit=audit)
    first = await service.save_version(project_id=project.id, tenant_id=TENANT_A, definition=VALID_WORKFLOW)
    second = await service.save_version(project_id=project.id, tenant_id=TENANT_A, definition=VALID_WORKFLOW)
    published = await service.publish(
        project_id=project.id, tenant_id=TENANT_A, actor_user_id=42, version=second.version
    )
    assert published.active_version == 2
    assert store.versions[(project.id, 2)].published_at is not None
    rolled_back = await service.rollback(
        project_id=project.id, tenant_id=TENANT_A, actor_user_id=42, version=first.version
    )
    assert rolled_back.active_version == 1
    assert store.versions[(project.id, 1)].published_at is not None
    assert events[0].startswith("project.publish:")
    assert events[1].startswith("project.rollback:")


async def test_publish_rejects_missing_version() -> None:
    store = FakeProjectStore()
    project = Project(uuid4(), 42, "My Bot", TENANT_A)
    await store.create_project(project)
    service = ProjectService(store)
    with pytest.raises(VersionNotFoundError):
        await service.publish(project_id=project.id, tenant_id=TENANT_A, actor_user_id=42, version=99)
