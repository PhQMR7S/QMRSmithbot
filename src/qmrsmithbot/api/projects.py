from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status

from qmrsmithbot.api.dependencies import get_current_user_id, get_project_service
from qmrsmithbot.api.schemas import (
    ProjectCreateRequest,
    ProjectResponse,
    WorkflowVersionCreateRequest,
    WorkflowVersionResponse,
)
from qmrsmithbot.domain.models import BotProject, WorkflowVersion
from qmrsmithbot.projects.service import ProjectService

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def project_response(project: BotProject) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        owner_id=project.owner_id,
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
    owner_id: int = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
) -> ProjectResponse:
    project = await service.create_project(owner_id=owner_id, name=payload.name)
    return project_response(project)


@router.post(
    "/{project_id}/versions",
    response_model=WorkflowVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_workflow_version(
    project_id: UUID,
    payload: WorkflowVersionCreateRequest,
    owner_id: int = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
) -> WorkflowVersionResponse:
    version = await service.save_version(
        project_id=project_id,
        owner_id=owner_id,
        definition=payload.definition,
    )
    return version_response(version)


@router.post("/{project_id}/publish/{version}", response_model=ProjectResponse)
async def publish_workflow(
    project_id: UUID,
    version: int,
    owner_id: int = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
) -> ProjectResponse:
    project = await service.publish(project_id=project_id, owner_id=owner_id, version=version)
    return project_response(project)


@router.post("/{project_id}/rollback/{version}", response_model=ProjectResponse)
async def rollback_workflow(
    project_id: UUID,
    version: int,
    owner_id: int = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
) -> ProjectResponse:
    project = await service.rollback(project_id=project_id, owner_id=owner_id, version=version)
    return project_response(project)
