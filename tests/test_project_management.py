from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from qmrsmithbot.domain.models import BotStatus
from qmrsmithbot.projects.service import ProjectNotFoundError, ProjectStateError
from qmrsmithbot.projects.sqlalchemy_store import SQLAlchemyProjectStore


def project(status='stopped', version=1):
    return SimpleNamespace(id=uuid4(), owner_id=1, tenant_id=uuid4(), name='A',
                           active_version=version, status=status)


async def test_stop_and_resume_preserve_active_version():
    p = project('running')
    session = AsyncMock()
    session.scalar.side_effect = [p, p, object()]
    store = SQLAlchemyProjectStore(session)
    stopped = await store.set_running(project_id=p.id, tenant_id=p.tenant_id, running=False)
    assert stopped.status == BotStatus.STOPPED
    assert stopped.active_version == 1
    resumed = await store.set_running(project_id=p.id, tenant_id=p.tenant_id, running=True)
    assert resumed.status == BotStatus.RUNNING
    assert resumed.active_version == 1


@pytest.mark.parametrize('state,version', [('draft', None), ('error', 1), ('stopped', None)])
async def test_resume_requires_published_version(state, version):
    p = project(state, version)
    session = AsyncMock()
    session.scalar.side_effect = [p, None]
    with pytest.raises(ProjectStateError):
        await SQLAlchemyProjectStore(session).set_running(
            project_id=p.id, tenant_id=p.tenant_id, running=True)
    session.flush.assert_not_awaited()


async def test_foreign_project_cannot_be_changed():
    session = AsyncMock()
    session.scalar.return_value = None
    with pytest.raises(ProjectNotFoundError):
        await SQLAlchemyProjectStore(session).set_running(
            project_id=uuid4(), tenant_id=uuid4(), running=False)
    session.flush.assert_not_awaited()


async def test_search_escapes_wildcards_and_scopes_tenant():
    session = AsyncMock()
    session.scalars.return_value = []
    tenant_id = uuid4()
    await SQLAlchemyProjectStore(session).list_projects(
        tenant_id=tenant_id, query='100%_sale', limit=21, offset=0, status=BotStatus.DRAFT)
    statement = session.scalars.call_args.args[0]
    values = list(statement.compile().params.values())
    assert tenant_id in values
    assert '100/%/_sale' in values
    assert 21 in values
