"""Authenticated draft studio; web and native editors share the same records."""
import hashlib
import json
import re
from copy import deepcopy
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.api.dependencies import get_current_principal, get_current_tenant_id
from qmrsmithbot.auth.models import Permission, Principal
from qmrsmithbot.db.factory_models import BotFormSubmissionRecord, FactoryButtonRecord
from qmrsmithbot.db.models import User
from qmrsmithbot.db.session import get_session
from qmrsmithbot.factory.bot_management import BotManagement
from qmrsmithbot.factory.button_editor import ButtonEditor
from qmrsmithbot.factory.store import SQLFactoryStore
from qmrsmithbot.forms.schema import Form
from qmrsmithbot.telegram.inline_runtime import InlineBotError, compile_text_program

router = APIRouter(prefix='/api/v1/projects/{project_id}/studio', tags=['studio'])


class WelcomeDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    welcome: str = Field(min_length=1, max_length=3000)


class FormDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    form: Form


class ButtonDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    parent_id: UUID | None = None
    kind: Literal['section', 'text', 'url', 'file']
    title: str = Field(min_length=1, max_length=64)
    text: str | None = Field(default=None, max_length=3000)
    url: str | None = Field(default=None, max_length=3000)
    revision: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')

    def content(self):
        data = {'kind': self.kind, 'title': self.title.strip()}
        ButtonEditor.validate('title', self.title)
        for field in ('text', 'url'):
            value = getattr(self, field)
            required = self.kind == field
            if required:
                if value is None:
                    raise ValueError()
                ButtonEditor.validate(field, value)
                data[field] = value if field == 'text' else value.strip()
            elif value is not None:
                raise ValueError()
        for value in data.values():
            if re.search(r'\b[0-9]{5,16}:[A-Za-z0-9_-]{20,}\b', value):
                raise ValueError()
        return data


class Revision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: str = Field(pattern=r'^[0-9a-f]{64}$')


def revision(item):
    source = {'draft': item.draft, 'parent': str(item.parent_id), 'deleted': item.deleted}
    return hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def button_view(item):
    data = {key: item.draft[key] for key in ('kind', 'title', 'text', 'url') if key in item.draft}
    return {'id': str(item.id), 'parent_id': str(item.parent_id) if item.parent_id else None,
        **data, 'revision': revision(item), 'published': item.published is not None,
        'pending': item.draft != item.published or item.deleted,
        'file_ready': bool(item.draft.get('file_id'))}


class Studio:
    def __init__(self, manager):
        self.manager, self.session = manager, manager.session

    async def project(self, project_id, write=False):
        try:
            project = await self.manager.project(project_id,
                Permission.PROJECT_WRITE if write else Permission.PROJECT_READ, lock=write)
            version = await self.manager.latest(project_id)
            program = compile_text_program(version.definition)
            return project, version, program
        except InlineBotError:
            raise HTTPException(404, 'Project is unavailable') from None
        except ValueError:
            raise HTTPException(409, 'This workflow is not supported by the studio') from None

    async def overview(self, project_id):
        project, version, program = await self.project(project_id)
        return {'id':str(project.id), 'name':project.name, 'kind':program.kind,
            'version':version.version, 'active_version':project.active_version,
            'welcome':program.commands.get('start', ''), 'username':project.telegram_username,
            'status':project.status, 'form':program.form.model_dump(mode='json') if program.form else None, 'commands':len(program.commands)-1, 'replies':len(program.messages)}

    async def save_welcome(self, project_id, payload):
        _, version, _ = await self.project(project_id, True)
        if version.version != payload.version:
            raise HTTPException(409, 'The draft changed. Reload before saving.')
        if not payload.welcome.strip() or re.search(r'\b[0-9]{5,16}:[A-Za-z0-9_-]{20,}\b',payload.welcome):
            raise HTTPException(422, 'Invalid welcome text')
        await self.manager.save_content(project_id, welcome=payload.welcome)
        return await self.overview(project_id)

    async def save_form(self, project_id, payload):
        _, version, program = await self.project(project_id, True)
        if program.kind != 'form':
            raise HTTPException(409, 'This is not a form bot')
        if version.version != payload.version:
            raise HTTPException(409, 'The draft changed. Reload before saving.')
        raw = payload.form.model_dump(mode='json')
        if re.search(r'\b[0-9]{5,16}:[A-Za-z0-9_-]{20,}\b',json.dumps(raw)):
            raise HTTPException(422, 'Credentials cannot be included in a form')
        definition=deepcopy(version.definition)
        definition['variables']={'factory_kind':'form','form':raw}
        compile_text_program(definition)
        await self.manager.store.projects_service.save_version(project_id=project_id,
            tenant_id=self.manager.store.tenant_id,definition=definition)
        await self.manager.store.audit('factory.form.saved',project_id,
            self.manager.store.user.id,self.manager.store.tenant_id)
        return await self.overview(project_id)

    async def submissions_owner(self, project_id, write=False):
        project, _, program=await self.project(project_id,write)
        if program.kind!='form':
            raise HTTPException(409, 'This is not a form bot')
        if project.owner_id!=self.manager.store.user.id:
            raise HTTPException(403, 'Only the project owner may access submitted answers')
        return project

    async def submissions(self, project_id, offset):
        await self.submissions_owner(project_id)
        records=(await self.session.scalars(select(BotFormSubmissionRecord).where(
            BotFormSubmissionRecord.project_id==project_id).order_by(
                BotFormSubmissionRecord.created_at.desc(),BotFormSubmissionRecord.id.desc()).offset(offset).limit(6))).all()
        return {'items':[{'id':str(r.id),'visitor_id':r.visitor_id,'version':r.version,
            'created_at':r.created_at.isoformat(),'data':r.data} for r in records[:5]],'has_more':len(records)>5}

    async def delete_submission(self, project_id, submission_id):
        await self.submissions_owner(project_id,True)
        record=await self.session.scalar(select(BotFormSubmissionRecord).where(
            BotFormSubmissionRecord.id==submission_id,BotFormSubmissionRecord.project_id==project_id))
        if record is None:
            raise HTTPException(404, 'Submission is unavailable')
        await self.session.delete(record)
        await self.manager.store.audit('factory.form.submission_deleted',project_id,
            self.manager.store.user.id,self.manager.store.tenant_id)
        return {'deleted':True}

    async def buttons_project(self, project_id, write=False):
        project, _, program = await self.project(project_id, write)
        if program.kind != 'buttons':
            raise HTTPException(409, 'Button editing requires a button bot')
        return project

    async def item(self, project_id, item_id):
        item = await self.session.scalar(select(FactoryButtonRecord).where(
            FactoryButtonRecord.project_id == project_id, FactoryButtonRecord.id == item_id,
            FactoryButtonRecord.deleted.is_(False)))
        if item is None:
            raise HTTPException(404, 'Button is unavailable')
        return item

    async def listing(self, project_id, parent_id, offset):
        await self.buttons_project(project_id)
        folder = await self.item(project_id, parent_id) if parent_id else None
        if folder is not None and folder.draft['kind'] != 'section':
            raise HTTPException(422, 'Parent must be a section')
        items = (await self.session.scalars(select(FactoryButtonRecord).where(
            FactoryButtonRecord.project_id == project_id, FactoryButtonRecord.parent_id == parent_id,
            FactoryButtonRecord.deleted.is_(False)).order_by(FactoryButtonRecord.created_at,
                FactoryButtonRecord.id).offset(offset).limit(9))).all()
        return {'items':[button_view(item) for item in items[:8]], 'has_more':len(items)>8,
                'folder':button_view(folder) if folder is not None else None}

    async def save_button(self, project_id, item_id, payload):
        await self.buttons_project(project_id, True)
        try:
            content = payload.content()
        except ValueError:
            raise HTTPException(422, 'Check button label, content and HTTPS link') from None
        if payload.parent_id:
            parent = await self.item(project_id, payload.parent_id)
            if parent.draft['kind'] != 'section':
                raise HTTPException(422, 'Parent must be a section')
        existing = await self.session.get(FactoryButtonRecord, item_id)
        if existing is not None:
            if existing.project_id != project_id or existing.deleted:
                raise HTTPException(404, 'Button is unavailable')
            if existing.parent_id != payload.parent_id or existing.draft['kind'] != payload.kind:
                raise HTTPException(409, 'Button kind and parent cannot be changed')
            if payload.revision is None:
                # A retried creation with its client-generated ID must not create twice.
                if existing.draft == content:
                    return button_view(existing)
                raise HTTPException(409, 'Button already exists. Reload before saving.')
            if revision(existing) != payload.revision:
                raise HTTPException(409, 'The button changed. Reload before saving.')
            existing.draft = {**existing.draft, **content}
            item = existing
        else:
            if payload.revision is not None:
                raise HTTPException(404, 'Button is unavailable')
            item = FactoryButtonRecord(id=item_id, project_id=project_id,
                parent_id=payload.parent_id, draft=content, deleted=False)
            self.session.add(item)
        await self.session.flush()
        await self.manager.store.audit('factory.button.saved',project_id,
            self.manager.store.user.id,self.manager.store.tenant_id)
        return button_view(item)

    async def delete_button(self, project_id, item_id, payload):
        await self.buttons_project(project_id, True)
        item = await self.item(project_id, item_id)
        if revision(item) != payload.revision:
            raise HTTPException(409, 'The button changed. Reload before deleting.')
        item.deleted = True
        await self.session.flush()
        await self.manager.store.audit('factory.button.deleted',project_id,
            self.manager.store.user.id,self.manager.store.tenant_id)
        return {'deleted':True}


async def get_studio(principal: Annotated[Principal, Depends(get_current_principal)],
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    session: Annotated[AsyncSession, Depends(get_session)]):
    user = await session.get(User, principal.user_id)
    if user is None:
        raise HTTPException(401, 'Account is unavailable')
    return Studio(BotManagement(SQLFactoryStore(session, user, tenant_id)))


StudioDependency = Annotated[Studio, Depends(get_studio)]


@router.get('')
async def studio_overview(project_id: UUID, studio: StudioDependency):
    return await studio.overview(project_id)


@router.patch('')
async def studio_welcome(project_id: UUID, payload: WelcomeDraft, studio: StudioDependency):
    return await studio.save_welcome(project_id, payload)


@router.get('/buttons')
async def studio_buttons(project_id: UUID, studio: StudioDependency,
    parent_id: UUID | None = None, offset: int = Query(default=0, ge=0, le=2**31-1)):
    return await studio.listing(project_id, parent_id, offset)


@router.put('/buttons/{item_id}')
async def studio_save_button(project_id: UUID, item_id: UUID, payload: ButtonDraft, studio: StudioDependency):
    return await studio.save_button(project_id, item_id, payload)


@router.post('/buttons/{item_id}/delete')
async def studio_delete_button(project_id: UUID, item_id: UUID, payload: Revision, studio: StudioDependency):
    return await studio.delete_button(project_id, item_id, payload)


@router.put('/form')
async def studio_save_form(project_id: UUID, payload: FormDraft, studio: StudioDependency):
    return await studio.save_form(project_id, payload)


@router.get('/submissions')
async def studio_submissions(project_id: UUID, studio: StudioDependency,
    offset: int = Query(default=0, ge=0, le=2**31-1)):
    return await studio.submissions(project_id, offset)


@router.post('/submissions/{submission_id}/delete')
async def studio_delete_submission(project_id: UUID, submission_id: UUID, studio: StudioDependency):
    return await studio.delete_submission(project_id, submission_id)
