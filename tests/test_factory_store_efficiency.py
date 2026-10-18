from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from qmrsmithbot.auth.models import Permission
from qmrsmithbot.factory.menu import MenuState
from qmrsmithbot.factory.store import SQLFactoryStore


async def test_conversation_is_loaded_once_and_returned_as_detached_data():
    record = SimpleNamespace(step='idle',data={'_ui':{'layout':'cards'}})
    session=AsyncMock()
    session.get.return_value=record
    store=SQLFactoryStore(session,SimpleNamespace(id=42),uuid4())
    first=await store.state()
    first.data['_ui']['layout']='list'
    assert (await store.state()).data['_ui']['layout']=='cards'
    await store.save_state(MenuState('next',{}))
    assert (await store.state()).step=='next'
    session.get.assert_awaited_once()
    assert record.data['_ui']['layout']=='cards'


async def test_permission_cache_is_scoped_to_one_store_transaction(monkeypatch):
    require=AsyncMock()
    monkeypatch.setattr('qmrsmithbot.factory.store.AuthorizationService.require_permission',require)
    session=AsyncMock()
    tenant=uuid4()
    store=SQLFactoryStore(session,SimpleNamespace(id=42),tenant)
    await store.permission(Permission.PROJECT_READ)
    await store.permission(Permission.PROJECT_READ)
    assert require.await_count==1
    await SQLFactoryStore(session,SimpleNamespace(id=42),tenant).permission(Permission.PROJECT_READ)
    assert require.await_count==2
