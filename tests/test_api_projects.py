from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from qmrsmithbot.api.app import app
from qmrsmithbot.api.dependencies import get_current_user_id, get_project_service
from qmrsmithbot.domain.models import BotProject, WorkflowVersion
from qmrsmithbot.projects.service import ProjectService

VALID_WORKFLOW = {
    "nodes": [
        {"id": "start", "type": "trigger.command"},
        {"id": "reply", "type": "action.message"},
    ],
    "edges": [{"source": "start", "target": "reply"}],
}


class FakeProjectStore:
    def __init__(self) -> None:
        self.projects: dict[UUID, BotProject] = {}
        self.versions: dict[tuple[UUID, int], WorkflowVersion] = {}

    async def create_project(self, project: BotProject) -> BotProject:
        self.projects[project.id] = project
        return project

    async def get_project_for_owner(self, project_id: UUID, owner_id: int) -> BotProject | None:
        project = self.projects.get(project_id)
        return project if project is not None and project.owner_id == owner_id else None

    async def create_next_version(
        self, project_id: UUID, definition: dict, version_id: UUID
    ) -> WorkflowVersion:
        versions = [
            version
            for (stored_project_id, _), version in self.versions.items()
            if stored_project_id == project_id
        ]
        next_version = max((version.version for version in versions), default=0) + 1
        created = WorkflowVersion(version_id, project_id, next_version, definition)
        self.versions[(project_id, next_version)] = created
        return created

    async def get_version(self, project_id: UUID, version: int) -> WorkflowVersion | None:
        return self.versions.get((project_id, version))

    async def list_versions(self, project_id: UUID) -> list[WorkflowVersion]:
        return sorted(
            (
                version
                for (stored_project_id, _), version in self.versions.items()
                if stored_project_id == project_id
            ),
            key=lambda version: version.version,
            reverse=True,
        )

    async def activate_version(self, project_id: UUID, version: int) -> BotProject:
        project = self.projects[project_id]
        updated = BotProject(project.id, project.owner_id, project.name, version)
        self.projects[project_id] = updated
        return updated


@pytest.fixture
def client() -> Iterator[TestClient]:
    store = FakeProjectStore()
    service = ProjectService(store)
    app.dependency_overrides[get_current_user_id] = lambda: 42
    app.dependency_overrides[get_project_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user_id, None)
        app.dependency_overrides.pop(get_project_service, None)


def test_create_project_endpoint(client: TestClient) -> None:
    response = client.post("/api/v1/projects", json={"name": "  API Bot  "})

    assert response.status_code == 201
    body = response.json()
    assert body["owner_id"] == 42
    assert body["name"] == "API Bot"
    assert body["status"] == "draft"


def test_workflow_lifecycle_endpoints(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Lifecycle Bot"}).json()
    project_id = project["id"]

    created = client.post(
        f"/api/v1/projects/{project_id}/versions",
        json={"definition": VALID_WORKFLOW},
    )
    assert created.status_code == 201
    assert created.json()["version"] == 1

    versions = client.get(f"/api/v1/projects/{project_id}/versions")
    assert versions.status_code == 200
    assert [item["version"] for item in versions.json()] == [1]

    fetched = client.get(f"/api/v1/projects/{project_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == project_id

    published = client.post(f"/api/v1/projects/{project_id}/publish/1")
    assert published.status_code == 200
    assert published.json()["active_version"] == 1


def test_missing_owner_identity_is_rejected() -> None:
    response = TestClient(app).post("/api/v1/projects", json={"name": "No Auth"})
    assert response.status_code == 401
