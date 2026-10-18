from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiogram.types import InlineKeyboardMarkup

from qmrsmithbot.factory.menu import FactoryMenu, MenuState
from qmrsmithbot.forms.schema import Form
from qmrsmithbot.telegram.child_forms import ChildFormEditor
from qmrsmithbot.telegram.inline_runtime import InlineBotError
from qmrsmithbot.templates.catalog import TemplateOptions, get_template


def editor():
    class Store:
        project_id=uuid4()
        tenant_id=uuid4()
        user=SimpleNamespace(id=42)
        conversation=MenuState('idle',{})
        version=1
        definition=get_template('form').build(TemplateOptions()).model_dump(mode='json')
        audit=AsyncMock()

        async def state(self):
            return self.conversation

        async def save_state(self,state):
            self.conversation=state

        async def save_version(self,**kwargs):
            self.definition=deepcopy(kwargs['definition'])
            self.version+=1
    store=Store()
    store.projects_service=SimpleNamespace(save_version=store.save_version)
    async def latest(_):
        return SimpleNamespace(version=store.version,definition=deepcopy(store.definition))
    manager=SimpleNamespace(store=store,project=AsyncMock(),latest=latest)
    menu=FactoryMenu(store,telegram_id=42)
    return ChildFormEditor(manager,menu),store


async def test_native_form_editor_preserves_versions_paths_and_validation():
    e,store=editor()
    home=await e.handle(action='fe:home')
    InlineKeyboardMarkup.model_validate(home['reply_markup'])
    await e.handle(action='fe:add:1:choice')
    await e.handle(text='اختر مسارك')
    assert store.version==2
    await e.handle(action='fe:up:2:2')
    assert store.version==3
    form=Form.model_validate(store.definition['variables']['form'])
    target=form.questions[2].id
    await e.handle(action=f'fe:target:3:1:0:{target}')
    assert store.version==4
    with pytest.raises(ValueError):
        await e.handle(action='fe:down:4:1')
    assert store.version==4
    ask=await e.handle(action='fe:delete:4:2')
    delete=ask['reply_markup']['inline_keyboard'][0][0]['callback_data']
    with pytest.raises(ValueError):
        await e.handle(action=delete)
    assert store.version==4
    with pytest.raises(InlineBotError):
        await e.handle(action='fe:required:3:0')
    await e.handle(action='fe:choices:4:1')
    with pytest.raises(ValueError):
        await e.handle(text='Same\nSame')
    assert store.version==4 and store.conversation.step=='child_form_input'
    await e.handle(text='Yes\nNo')
    assert store.version==5
    assert all(c.next is None for c in Form.model_validate(store.definition['variables']['form']).questions[1].choices)
    await e.handle(action='fe:settype:5:0:number')
    await e.handle(action='fe:limits:6:0')
    with pytest.raises(ValueError):
        await e.handle(text='nan 100')
    await e.handle(text='18 65')
    q=Form.model_validate(store.definition['variables']['form']).questions[0]
    assert q.minimum==18 and q.maximum==65 and store.version==7
    await e.handle(action='fe:required:7:0')
    assert Form.model_validate(store.definition['variables']['form']).questions[0].required is False


@pytest.mark.parametrize('callback',['fe:branch:1:0','fe:target:1:0:0','fe:q:1:999','fe:unknown:1:0'])
async def test_malformed_form_controls_do_not_persist(callback):
    e,store=editor()
    with pytest.raises(ValueError):
        await e.handle(action=callback)
    assert store.version==1
