from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiogram.types import InlineKeyboardMarkup, Update

from qmrsmithbot.factory.menu import MenuState
from qmrsmithbot.telegram.child_control import (
    ChildManagement,
    ChildStore,
    child_control,
    localize_panel,
)
from qmrsmithbot.telegram.inline_runtime import InlineBotError


async def test_bound_manager_rejects_another_project_before_any_query():
    store=SimpleNamespace(project_id=uuid4(),session=SimpleNamespace(scalar=AsyncMock()))
    manager=ChildManagement(store)
    with pytest.raises(InlineBotError):
        await manager.project(uuid4())
    with pytest.raises(InlineBotError):
        await manager.latest(uuid4())
    store.session.scalar.assert_not_awaited()


async def test_child_state_preserves_upload_and_does_not_use_global_conversation():
    record=SimpleNamespace(data={'upload':'file','control':{'step':'bot_welcome','data':{'value':'old'}}})
    session=SimpleNamespace(get=AsyncMock(return_value=record),flush=AsyncMock())
    store=ChildStore(session,SimpleNamespace(id=42),SimpleNamespace(id=uuid4(),tenant_id=uuid4()))
    state=await store.state()
    state.data['value']='changed'
    assert record.data['control']['data']['value']=='old'
    await store.save_state(MenuState('idle',{}))
    assert record.data['upload']=='file'
    assert record.data['control']=={'step':'idle','data':{}}


def test_local_navigation_does_not_expose_factory_management():
    project=SimpleNamespace(id=uuid4())
    response={'text':'Panel','reply_markup':{'inline_keyboard':[
        [{'text':'Other bots','callback_data':'projects:0'},{'text':'Connect','callback_data':'connection:'+str(project.id)}],
        [{'text':'Admin','callback_data':'admin'}],
        [{'text':'Edit','callback_data':'welcome:'+str(project.id)}]]}}
    localized=localize_panel(response,project,'ar')
    callbacks=[b['callback_data'] for row in localized['reply_markup']['inline_keyboard'] for b in row]
    assert all(data.startswith('ca:') for data in callbacks)
    assert not any('projects:' in data or 'connection:' in data for data in callbacks)
    assert 'ca:welcome:'+str(project.id) in callbacks
    assert response['reply_markup']['inline_keyboard'][0][0]['callback_data']=='projects:0'
    InlineKeyboardMarkup.model_validate(localized['reply_markup'])


async def test_foreign_authored_admin_callback_is_ignored_before_reading_secrets():
    update=Update.model_validate({'update_id':1,'callback_query':{'id':'1','from':{'id':42,'is_bot':False,'first_name':'A'},
        'chat_instance':'x','data':'ca:project:'+str(uuid4()),'message':{'message_id':1,'date':1,
        'chat':{'id':42,'type':'private'},'from':{'id':99,'is_bot':False,'first_name':'User'},'text':'fake'}}})
    session=SimpleNamespace(get=AsyncMock())
    assert await child_control(session,SimpleNamespace(telegram_bot_id=100),update)==(True,None)
    session.get.assert_not_awaited()


async def test_whitespace_message_is_not_a_management_command():
    update=Update.model_validate({'update_id':1,'message':{'message_id':1,'date':1,
        'chat':{'id':42,'type':'private'},'from':{'id':42,'is_bot':False,'first_name':'A'},'text':'   '}})
    session=SimpleNamespace(get=AsyncMock(return_value=None))
    assert await child_control(session,SimpleNamespace(id=uuid4()),update)==(False,None)
