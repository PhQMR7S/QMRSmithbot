from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from qmrsmithbot.api.dependencies import (
    get_authorization_service,
    get_current_principal,
    get_current_tenant_id,
    get_project_service,
)
from qmrsmithbot.api.schemas import (
    ProjectCreateRequest,
    ProjectResponse,
    WorkflowVersionCreateRequest,
    WorkflowVersionResponse,
)
from qmrsmithbot.auth.authorization import AuthorizationService
from qmrsmithbot.auth.models import Permission, Principal
from qmrsmithbot.domain.models import BotProject, BotStatus, WorkflowVersion
from qmrsmithbot.projects.service import ProjectService

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])
CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
CurrentTenantId = Annotated[UUID, Depends(get_current_tenant_id)]
AuthorizationDependency = Annotated[AuthorizationService, Depends(get_authorization_service)]
ProjectServiceDependency = Annotated[ProjectService, Depends(get_project_service)]


def project_response(project: BotProject) -> ProjectResponse:
    if project.tenant_id is None:
        raise RuntimeError("project is missing tenant scope")
    return ProjectResponse(
        id=project.id,
        owner_id=project.owner_id,
        tenant_id=project.tenant_id,
        name=project.name,
        active_version=project.active_version,
        status=project.status,
    )


def version_response(version: WorkflowVersion) -> WorkflowVersionResponse:
    return WorkflowVersionResponse(
        id=version.id,
        project_id=version.project_id,
        version=version.version,
        definition=version.definition,
        published_at=version.published_at,
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreateRequest,
    principal: CurrentPrincipal,
    tenant_id: CurrentTenantId,
    authorization: AuthorizationDependency,
    service: ProjectServiceDependency,
) -> ProjectResponse:
    await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.PROJECT_WRITE
    )
    project = await service.create_project(
        owner_id=principal.user_id, tenant_id=tenant_id, name=payload.name
    )
    return project_response(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    principal: CurrentPrincipal,
    tenant_id: CurrentTenantId,
    authorization: AuthorizationDependency,
    service: ProjectServiceDependency,
) -> ProjectResponse:
    await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.PROJECT_READ
    )
    project = await service.get_project(project_id=project_id, tenant_id=tenant_id)
    return project_response(project)


@router.get("/{project_id}/versions", response_model=list[WorkflowVersionResponse])
async def list_workflow_versions(
    project_id: UUID,
    principal: CurrentPrincipal,
    tenant_id: CurrentTenantId,
    authorization: AuthorizationDependency,
    service: ProjectServiceDependency,
) -> list[WorkflowVersionResponse]:
    await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.PROJECT_READ
    )
    versions = await service.list_versions(project_id=project_id, tenant_id=tenant_id)
    return [version_response(version) for version in versions]


@router.post(
    "/{project_id}/versions",
    response_model=WorkflowVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_workflow_version(
    project_id: UUID,
    payload: WorkflowVersionCreateRequest,
    principal: CurrentPrincipal,
    tenant_id: CurrentTenantId,
    authorization: AuthorizationDependency,
    service: ProjectServiceDependency,
) -> WorkflowVersionResponse:
    await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.PROJECT_WRITE
    )
    version = await service.save_version(
        project_id=project_id, tenant_id=tenant_id, definition=payload.definition
    )
    return version_response(version)


@router.post("/{project_id}/publish/{version}", response_model=ProjectResponse)
async def publish_workflow(
    project_id: UUID,
    version: int,
    principal: CurrentPrincipal,
    tenant_id: CurrentTenantId,
    authorization: AuthorizationDependency,
    service: ProjectServiceDependency,
) -> ProjectResponse:
    await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.PROJECT_PUBLISH
    )
    project = await service.publish(
        project_id=project_id,
        tenant_id=tenant_id,
        actor_user_id=principal.user_id,
        version=version,
    )
    return project_response(project)


@router.post("/{project_id}/rollback/{version}", response_model=ProjectResponse)
async def rollback_workflow(
    project_id: UUID,
    version: int,
    principal: CurrentPrincipal,
    tenant_id: CurrentTenantId,
    authorization: AuthorizationDependency,
    service: ProjectServiceDependency,
) -> ProjectResponse:
    await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.PROJECT_PUBLISH
    )
    project = await service.rollback(
        project_id=project_id,
        tenant_id=tenant_id,
        actor_user_id=principal.user_id,
        version=version,
    )
    return project_response(project)


class RenameProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name must not be blank")
        return value.strip()


class ProjectPage(BaseModel):
    items: list[ProjectResponse]
    limit: int
    offset: int
    has_more: bool


@router.get("", response_model=ProjectPage)
async def list_projects(
    principal: CurrentPrincipal, tenant_id: CurrentTenantId,
    authorization: AuthorizationDependency, service: ProjectServiceDependency,
    query: Annotated[str, Query(max_length=120)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    project_status: Annotated[BotStatus | None, Query(alias="status")] = None,
) -> ProjectPage:
    await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.PROJECT_READ
    )
    projects = await service.list_projects(
        tenant_id=tenant_id, query=query, limit=limit + 1, offset=offset, status=project_status
    )
    return ProjectPage(items=[project_response(p) for p in projects[:limit]],
                       limit=limit, offset=offset, has_more=len(projects) > limit)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def rename_project(
    project_id: UUID, payload: RenameProjectRequest, principal: CurrentPrincipal,
    tenant_id: CurrentTenantId, authorization: AuthorizationDependency,
    service: ProjectServiceDependency,
) -> ProjectResponse:
    await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.PROJECT_WRITE
    )
    return project_response(await service.rename(
        project_id=project_id, tenant_id=tenant_id, name=payload.name,
        actor_user_id=principal.user_id,
    ))


@router.post("/{project_id}/stop", response_model=ProjectResponse)
async def stop_project(
    project_id: UUID, principal: CurrentPrincipal, tenant_id: CurrentTenantId,
    authorization: AuthorizationDependency, service: ProjectServiceDependency,
) -> ProjectResponse:
    await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.PROJECT_PUBLISH
    )
    return project_response(await service.set_running(
        project_id=project_id, tenant_id=tenant_id, running=False, actor_user_id=principal.user_id
    ))


@router.post("/{project_id}/resume", response_model=ProjectResponse)
async def resume_project(
    project_id: UUID, principal: CurrentPrincipal, tenant_id: CurrentTenantId,
    authorization: AuthorizationDependency, service: ProjectServiceDependency,
) -> ProjectResponse:
    await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.PROJECT_PUBLISH
    )
    return project_response(await service.set_running(
        project_id=project_id, tenant_id=tenant_id, running=True, actor_user_id=principal.user_id
    ))
