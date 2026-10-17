from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from qmrsmithbot.api.app import app
from qmrsmithbot.api.dependencies import (
    get_authorization_service,
    get_current_principal,
    get_current_tenant_id,
    get_project_service,
)
from qmrsmithbot.auth.models import Permission, Principal
from qmrsmithbot.domain.models import BotProject, WorkflowVersion
from qmrsmithbot.projects.service import ProjectService

VALID_WORKFLOW = {
    "nodes": [
        {"id": "start", "type": "trigger.command"},
        {"id": "reply", "type": "action.message"},
    ],
    "edges": [{"source": "start", "target": "reply"}],
}
TENANT_ID = uuid4()


class FakeProjectStore:
    def __init__(self) -> None:
        self.projects: dict[UUID, BotProject] = {}
        self.versions: dict[tuple[UUID, int], WorkflowVersion] = {}

    async def create_project(self, project: BotProject) -> BotProject:
        self.projects[project.id] = project
        return project

    async def list_projects(self, *, tenant_id, query, limit, offset, status):
        projects = sorted((p for p in self.projects.values()
                           if p.tenant_id == tenant_id and query.casefold() in p.name.casefold()
                           and (status is None or p.status == status)), key=lambda p: p.id)
        return projects[offset:offset + limit]

    async def rename_project(self, *, project_id, tenant_id, name):
        from dataclasses import replace

        from qmrsmithbot.projects.service import ProjectNotFoundError
        p = await self.get_project_for_tenant(project_id, tenant_id)
        if p is None:
            raise ProjectNotFoundError('project was not found')
        self.projects[p.id] = replace(p, name=name)
        return self.projects[p.id]

    async def get_project_for_tenant(self, project_id: UUID, tenant_id: UUID) -> BotProject | None:
        project = self.projects.get(project_id)
        return project if project is not None and project.tenant_id == tenant_id else None

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
        updated = BotProject(
            project.id,
            project.owner_id,
            project.name,
            project.tenant_id,
            version,
            project.status,
        )
        self.projects[project_id] = updated
        return updated


class FakeAuthorizationService:
    async def require_permission(self, *, user_id: int, tenant_id: UUID, permission: Permission):
        return None


@pytest.fixture
def client() -> Iterator[TestClient]:
    store = FakeProjectStore()
    service = ProjectService(store)
    principal = Principal(user_id=42, session_id=uuid4())
    app.dependency_overrides[get_current_principal] = lambda: principal
    app.dependency_overrides[get_current_tenant_id] = lambda: TENANT_ID
    app.dependency_overrides[get_authorization_service] = FakeAuthorizationService
    app.dependency_overrides[get_project_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        for dependency in (
            get_current_principal,
            get_current_tenant_id,
            get_authorization_service,
            get_project_service,
        ):
            app.dependency_overrides.pop(dependency, None)


def test_create_project_endpoint(client: TestClient) -> None:
    response = client.post("/api/v1/projects", json={"name": "  API Bot  "})
    assert response.status_code == 201
    body = response.json()
    assert body["owner_id"] == 42
    assert body["tenant_id"] == str(TENANT_ID)
    assert body["name"] == "API Bot"
    assert body["status"] == "draft"


def test_workflow_lifecycle_endpoints(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Lifecycle Bot"}).json()
    project_id = project["id"]
    created = client.post(
        f"/api/v1/projects/{project_id}/versions", json={"definition": VALID_WORKFLOW}
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


def test_missing_session_is_rejected() -> None:
    response = TestClient(app).post("/api/v1/projects", json={"name": "No Auth"})
    assert response.status_code == 401


def test_template_catalog_and_draft_creation(client):
    catalog = client.get('/api/v1/templates?language_code=en')
    assert catalog.status_code == 200
    assert len(catalog.json()) == 3
    response = client.post('/api/v1/templates/auto-replies/projects', json={
        'name': 'FAQ', 'rules': [{'trigger': 'price', 'response': 'Ask our team'}]})
    assert response.status_code == 201
    body = response.json()
    assert body['owner_id'] == 42
    assert body['tenant_id'] == str(TENANT_ID)
    assert body['status'] == 'draft'
    assert body['active_version'] is None
    assert body['draft_version']['version'] == 1
    assert body['draft_version']['published_at'] is None


def test_templates_reject_invalid_requests(client):
    for template, payload, code in [
        ('missing', {'name': 'A'}, 404),
        ('welcome', {'name': '   '}, 422),
        ('auto-replies', {'name': 'A'}, 422),
        ('command-menu', {'name': 'A', 'rules': [{'trigger': 'start', 'response': 'x'}]}, 422),
        ('welcome', {'name': 'A', 'owner_id': 9}, 422),
    ]:
        assert client.post(f'/api/v1/templates/{template}/projects', json=payload).status_code == code


def test_template_authentication_required():
    c = TestClient(app)
    assert c.get('/api/v1/templates').status_code == 401
    assert c.post('/api/v1/templates/welcome/projects', json={'name': 'A'}).status_code == 401


def test_template_permission_is_required(client):
    from qmrsmithbot.auth.authorization import AuthorizationDenied

    class Denied:
        async def require_permission(self, **kwargs):
            raise AuthorizationDenied('Permission denied')

    app.dependency_overrides[get_authorization_service] = Denied
    assert client.post('/api/v1/templates/welcome/projects', json={'name': 'A'}).status_code == 403


def test_no_fixed_five_project_limit(client):
    for index in range(6):
        response = client.post('/api/v1/templates/welcome/projects', json={'name': f'Bot {index}'})
        assert response.status_code == 201



def test_project_search_pagination_and_rename(client):
    created = [client.post('/api/v1/projects', json={'name': f'Item {i}'}).json() for i in range(3)]
    first = client.get('/api/v1/projects?query=item&limit=2').json()
    second = client.get('/api/v1/projects?query=item&limit=2&offset=2').json()
    assert first['has_more'] is True
    assert second['has_more'] is False
    ids = [p['id'] for p in first['items'] + second['items']]
    assert set(ids) == {p['id'] for p in created}
    assert len(ids) == len(set(ids))
    target = created[0]['id']
    assert client.patch(f'/api/v1/projects/{target}', json={'name': ' Renamed '}).json()['name'] == 'Renamed'
    assert len(client.get('/api/v1/projects?query=renamed').json()['items']) == 1
    assert client.patch(f'/api/v1/projects/{target}', json={'name': ' '}).status_code == 422
    assert client.patch(f'/api/v1/projects/{uuid4()}', json={'name': 'Other'}).status_code == 404


@pytest.mark.parametrize('query', ['limit=0', 'limit=101', 'offset=-1', 'status=invalid'])
def test_invalid_project_filters(client, query):
    assert client.get('/api/v1/projects?' + query).status_code == 422


@pytest.mark.parametrize('action', ['stop', 'resume'])
def test_project_lifecycle_permission_denied(client, action):
    from qmrsmithbot.auth.authorization import AuthorizationDenied

    class Denied:
        async def require_permission(self, **kwargs):
            raise AuthorizationDenied('Permission denied')

    app.dependency_overrides[get_authorization_service] = Denied
    assert client.post(f'/api/v1/projects/{uuid4()}/{action}').status_code == 403


@pytest.mark.parametrize('action,running', [('stop', False), ('resume', True)])
def test_project_lifecycle_routes_forward_authenticated_scope(client, action, running):
    from unittest.mock import AsyncMock

    service = AsyncMock()
    project_id = uuid4()
    service.set_running.return_value = BotProject(
        id=project_id, owner_id=42, tenant_id=TENANT_ID, name='A',
        active_version=1, status='running' if running else 'stopped')
    app.dependency_overrides[get_project_service] = lambda: service
    assert client.post(f'/api/v1/projects/{project_id}/{action}').status_code == 200
    service.set_running.assert_awaited_once_with(
        project_id=project_id, tenant_id=TENANT_ID, running=running, actor_user_id=42)
