from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiogram.methods import EditMessageText, SendRichMessage

from qmrsmithbot.factory.menu import MenuState
from qmrsmithbot.factory.presentation import telegram_response
from qmrsmithbot.telegram.child_control import ChildStore
from qmrsmithbot.telegram.feature_guide import feature_guide
from qmrsmithbot.telegram.ready_copy import prepared_copy


@pytest.mark.parametrize('language',['ar','en'])
@pytest.mark.parametrize('kind',['buttons','form','contact','text'])
def test_prepared_copy_matches_capability_and_respects_field_lengths(language,kind):
    options=prepared_copy(kind,'QMR7S',language)
    assert len({o.id for o in options})==len(options)
    for option in options:
        assert 0<len(option.text)<= (1000 if option.target=='completion' else 3000)
        assert '{' not in option.text
    assert any(o.target=='completion' for o in options)==(kind=='form')
    assert any(o.target=='button' for o in options)==(kind=='buttons')
    if kind=='contact':
        assert ('رموز تسجيل الدخول' if language=='ar' else 'login codes') in options[0].text


async def test_child_rich_preference_survives_direct_editor_state_writes():
    record=SimpleNamespace(data={'control':{'step':'idle','data':{'_ui':{'rich':True}}}})
    store=ChildStore(SimpleNamespace(get=AsyncMock(return_value=record),flush=AsyncMock()),
        SimpleNamespace(id=42),SimpleNamespace(id=uuid4(),tenant_id=uuid4()))
    await store.save_state(MenuState('bot_welcome',{'project_id':'x'}))
    assert (await store.state()).data['_ui']['rich'] is True
    await store.save_state(MenuState('idle',{'_ui':{'rich':False}}))
    assert (await store.state()).data['_ui']['rich'] is False


def test_rich_feature_panel_is_escaped_and_validates_with_telegram_models():
    response=feature_guide('ar',child=True)
    command=telegram_response(response,actor_id=42,callback=None,bot_id=99,rich=True)
    SendRichMessage.model_validate(command)
    assert 'غير' in command['rich_message']['html'] or 'ليست' in command['rich_message']['html']
    callback=SimpleNamespace(message=SimpleNamespace(message_id=1,from_user=SimpleNamespace(id=99,is_bot=True)))
    EditMessageText.model_validate(telegram_response(response,actor_id=42,callback=callback,bot_id=99,rich=True))
