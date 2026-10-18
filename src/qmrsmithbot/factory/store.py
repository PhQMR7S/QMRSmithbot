import secrets
from copy import deepcopy
from datetime import UTC, datetime

from sqlalchemy import select

from qmrsmithbot.auth.authorization import AuthorizationService
from qmrsmithbot.auth.models import Permission
from qmrsmithbot.auth.service import TenantService
from qmrsmithbot.db.factory_models import FactoryConversationRecord
from qmrsmithbot.db.models import AuditEvent, IdentityRecord, User
from qmrsmithbot.factory.menu import MenuState
from qmrsmithbot.localization import resolve_language
from qmrsmithbot.projects.service import ProjectNotFoundError, ProjectService
from qmrsmithbot.projects.sqlalchemy_store import SQLAlchemyProjectStore


async def telegram_identity(session, actor):
    """Caller holds a per-Telegram-user transaction lock. Never equate external and internal IDs."""
    identity = await session.scalar(select(IdentityRecord).where(
        IdentityRecord.provider == 'telegram', IdentityRecord.subject == str(actor.id)))
    if identity is not None:
        user = await session.get(User, identity.user_id)
        if user is None:
            raise RuntimeError('Telegram identity has no account')
        identity.last_authenticated_at = datetime.now(UTC)
        return user
    while True:
        user_id = secrets.randbelow(2**62 - 1) + 1
        if await session.get(User, user_id) is None:
            break
    user = User(id=user_id, username=actor.username, first_name=actor.first_name,
                language_code=resolve_language(None, actor.language_code))
    session.add(user)
    await session.flush()
    session.add(IdentityRecord(user_id=user_id, provider='telegram', subject=str(actor.id),
                               last_authenticated_at=datetime.now(UTC)))
    await session.flush()
    return user


class SQLFactoryStore:
    def __init__(self, session, user, tenant_id):
        self.session, self.user, self.tenant_id = session, user, tenant_id
        self._conversation_loaded = False
        self._conversation = None
        self._permissions = set()
        self.projects_service = ProjectService(SQLAlchemyProjectStore(session), audit=self.audit)

    async def audit(self, action, project_id, actor_user_id, tenant_id):
        self.session.add(AuditEvent(actor_user_id=actor_user_id, tenant_id=tenant_id,
                                    project_id=project_id, action=action))
        await self.session.flush()

    async def language(self):
        return resolve_language(self.user.language_code)

    async def set_language(self, language):
        self.user.language_code = language
        await self.session.flush()

    async def _conversation_record(self):
        if not self._conversation_loaded:
            self._conversation = await self.session.get(FactoryConversationRecord, self.user.id)
            self._conversation_loaded = True
        return self._conversation

    async def state(self):
        record = await self._conversation_record()
        return MenuState(record.step, deepcopy(record.data)) if record else MenuState('idle', {})

    async def save_state(self, state):
        record = await self._conversation_record()
        if record is None:
            record = FactoryConversationRecord(user_id=self.user.id)
            self.session.add(record)
            self._conversation = record
        preferences = (record.data or {}).get('_ui', {})
        record.step, record.data = state.step, {**state.data, '_ui': state.data.get('_ui', preferences)}
        await self.session.flush()

    async def permission(self, permission):
        if permission in self._permissions:
            return
        await AuthorizationService(self.session).require_permission(
            user_id=self.user.id, tenant_id=self.tenant_id, permission=permission)
        self._permissions.add(permission)

    async def projects(self, *, offset, limit):
        await self.permission(Permission.PROJECT_READ)
        return await self.projects_service.list_projects(
            tenant_id=self.tenant_id, offset=offset, limit=limit)

    async def project(self, project_id):
        await self.permission(Permission.PROJECT_READ)
        try:
            return await self.projects_service.get_project(project_id=project_id, tenant_id=self.tenant_id)
        except ProjectNotFoundError:
            return None

    async def set_running(self, project_id, running):
        await self.permission(Permission.PROJECT_PUBLISH)
        return await self.projects_service.set_running(project_id=project_id, tenant_id=self.tenant_id,
                    running=running, actor_user_id=self.user.id)

    async def create(self, name, definition, *, starter=None):
        await self.permission(Permission.PROJECT_WRITE)
        if starter:
            from qmrsmithbot.factory.starters import get_starter
            from qmrsmithbot.telegram.inline_runtime import compile_text_program
            if get_starter(starter) is None or compile_text_program(definition).kind != 'buttons':
                raise ValueError('Invalid button starter')
        project = await self.projects_service.create_project(owner_id=self.user.id,
                    tenant_id=self.tenant_id, name=name)
        await self.projects_service.save_version(project_id=project.id, tenant_id=self.tenant_id,
                                                 definition=definition)
        if starter:
            from qmrsmithbot.factory.starters import starter_records
            self.session.add_all(starter_records(starter, project.id, await self.language()))
            await self.session.flush()
        await self.audit('factory.project.created', project.id, self.user.id, self.tenant_id)
        return project


async def factory_store(session, actor):
    user = await telegram_identity(session, actor)
    tenant = await TenantService(session).ensure_personal_tenant(user.id)
    return SQLFactoryStore(session, user, tenant.id)
