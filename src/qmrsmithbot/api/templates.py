from fastapi import APIRouter, HTTPException
from pydantic import Field, field_validator

from qmrsmithbot.api.projects import (
    AuthorizationDependency,
    CurrentPrincipal,
    CurrentTenantId,
    ProjectServiceDependency,
    project_response,
    version_response,
)
from qmrsmithbot.api.schemas import ProjectResponse, WorkflowVersionResponse
from qmrsmithbot.auth.models import Permission
from qmrsmithbot.localization import LanguageCode
from qmrsmithbot.templates.catalog import CATALOG, TemplateOptions, get_template

router = APIRouter(prefix='/api/v1/templates', tags=['templates'])


class TemplateProjectRequest(TemplateOptions):
    name: str = Field(min_length=1, max_length=120)

    @field_validator('name')
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Project name must not be blank')
        return value.strip()


class TemplateProjectResponse(ProjectResponse):
    template_id: str
    template_version: int
    draft_version: WorkflowVersionResponse


@router.get('')
async def list_templates(principal: CurrentPrincipal, language_code: LanguageCode = 'ar'):
    return [{'id': t.id, 'version': t.version, 'category': t.category,
             'title': t.title_ar if language_code == 'ar' else t.title_en,
             'status': 'draft_available', 'requires': ['telegram_bot_token', 'deployed_runtime']}
            for t in CATALOG]


@router.post('/{template_id}/projects', response_model=TemplateProjectResponse, status_code=201)
async def create_from_template(
    template_id: str,
    payload: TemplateProjectRequest,
    principal: CurrentPrincipal,
    tenant_id: CurrentTenantId,
    authorization: AuthorizationDependency,
    service: ProjectServiceDependency,
):
    await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.PROJECT_WRITE
    )
    try:
        template = get_template(template_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail='Template not found') from exc
    try:
        definition = template.build(payload).model_dump(mode='json')
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    project = await service.create_project(
        owner_id=principal.user_id, tenant_id=tenant_id, name=payload.name
    )
    version = await service.save_version(
        project_id=project.id, tenant_id=tenant_id, definition=definition
    )
    return TemplateProjectResponse(
        **project_response(project).model_dump(), template_id=template.id,
        template_version=template.version, draft_version=version_response(version),
    )
