from time import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from qmrsmithbot.factory.managed_bots import (
    confirm_binding,
    creation_url,
    pending_valid,
    prepare_creation,
    receive_managed,
)
from qmrsmithbot.factory.menu import MenuState
from qmrsmithbot.telegram.inline_runtime import InlineBotError


def test_pending_creation_expires_and_url_encodes_name():
    assert pending_valid(MenuState('managed_wait', {'expires': time()+30}))
    assert not pending_valid(MenuState('managed_wait', {'expires': time()-1}))
    assert not pending_valid(MenuState('idle', {'expires': time()+30}))
    url = urlsplit(creation_url('ManagerBot', 'اسم & test'))
    assert url.netloc == 't.me' and url.path.startswith('/newbot/ManagerBot/QMR_')
    assert parse_qs(url.query)['name'] == ['اسم & test']


def context():
    state = MenuState('managed_wait', {'project_id': str(uuid4()), 'expires': time()+300})
    store = SimpleNamespace(user=SimpleNamespace(id=42), state=AsyncMock(return_value=state))
    project = SimpleNamespace(id=uuid4(), owner_id=42, telegram_bot_id=None, name='My bot', status='draft')
    management = SimpleNamespace(store=store, session=SimpleNamespace(scalar=AsyncMock(return_value=None)),
        project=AsyncMock(return_value=project), bind=AsyncMock())
    menu = SimpleNamespace(telegram_id=123, save_state=AsyncMock(),
        response=lambda text, rows=None: {'text':text, 'rows':rows}, text=lambda key:key)
    event = SimpleNamespace(user=SimpleNamespace(id=123,is_bot=False),
        bot_user=SimpleNamespace(id=98765,is_bot=True,username='NewBot'))
    return management, menu, event, project


@pytest.mark.asyncio
async def test_event_requires_pending_owner_and_only_reserves_identity():
    management, menu, event, project = context()
    event.user.id = 999
    assert await receive_managed(management,menu,event) is None
    event.user.id = 123
    result = await receive_managed(management,menu,event)
    assert 'NewBot' in result['text']
    assert project.telegram_bot_id == 98765
    candidate = menu.save_state.call_args.args[0]
    assert candidate.step == 'managed_confirm' and candidate.data['bot_id'] == 98765
    management.bind.assert_not_called()
    management.store.state.return_value = MenuState('idle', {})
    assert await receive_managed(management,menu,event) is None


@pytest.mark.asyncio
async def test_disabled_management_offers_real_token_fallback(monkeypatch):
    management, menu, _, project = context()
    fake = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(can_manage_bots=False,username='ManagerBot')),
        session=SimpleNamespace(close=AsyncMock()))
    monkeypatch.setattr('qmrsmithbot.factory.bot_management.make_bot',lambda token:fake)
    result = await prepare_creation(management,menu,project)
    assert result['rows'][0][0]['callback_data'] == 'bind:'+str(project.id)
    menu.save_state.assert_not_called()
    fake.session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirmation_rejects_nonce_expiry_revocation_and_wrong_token(monkeypatch):
    management, menu, _, project = context()
    project.telegram_bot_id = 98765
    state = MenuState('managed_confirm', {'project_id':str(project.id),'bot_id':98765,'nonce':'ok','expires':time()+300})
    management.store.state.return_value = state
    assert (await confirm_binding(management,menu,'forged'))['text'] == 'invalid'
    fake = SimpleNamespace(get_managed_bot_token=AsyncMock(return_value='99999:'+'S'*35),
        session=SimpleNamespace(close=AsyncMock()))
    monkeypatch.setattr('qmrsmithbot.factory.bot_management.make_bot',lambda token:fake)
    with pytest.raises(InlineBotError):
        await confirm_binding(management,menu,'ok')
    management.bind.assert_not_called()
    fake.get_managed_bot_token.return_value = '98765:'+'S'*35
    await confirm_binding(management,menu,'ok')
    management.bind.assert_awaited_once()
    project.status = 'error'
    with pytest.raises(InlineBotError):
        await confirm_binding(management,menu,'ok')
    assert fake.get_managed_bot_token.await_count == 2


@pytest.mark.asyncio
async def test_ownership_change_disables_old_runtime_and_removes_credentials(monkeypatch):
    management, menu, event, project = context()
    management.session.scalar.return_value = project
    credential, runtime = object(), SimpleNamespace(enabled=True)
    management.session.get = AsyncMock(side_effect=[credential,runtime])
    management.session.delete = AsyncMock()
    monkeypatch.setattr('qmrsmithbot.factory.managed_bots.owner_telegram_id',AsyncMock(return_value=456))
    assert await receive_managed(management,menu,event) is None
    assert project.status == 'error' and runtime.enabled is False
    management.session.delete.assert_awaited_once_with(credential)
    management.bind.assert_not_called()


@pytest.mark.asyncio
async def test_profile_control_uses_bound_credentials_and_validates_limits(monkeypatch):
    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    from qmrsmithbot.config import settings
    from qmrsmithbot.factory.bot_management import BotManagement

    key = Fernet.generate_key()
    monkeypatch.setattr(settings,'telegram_credential_encryption_key',SecretStr(key.decode()))
    credential = SimpleNamespace(token_ciphertext=Fernet(key).encrypt(b'98765:secret').decode())
    store = SimpleNamespace(session=SimpleNamespace(get=AsyncMock(return_value=credential)),audit=AsyncMock(),
        user=SimpleNamespace(id=42),tenant_id=uuid4())
    management = BotManagement(store)
    management.project = AsyncMock()
    bot = SimpleNamespace(set_my_name=AsyncMock(return_value=True),set_my_description=AsyncMock(return_value=True),
        set_my_short_description=AsyncMock(return_value=True),session=SimpleNamespace(close=AsyncMock()))
    monkeypatch.setattr('qmrsmithbot.factory.bot_management.make_bot',lambda token:bot)
    project_id = uuid4()
    for field, text in [('name','اسم البوت'),('description','وصف'),('about','نبذة')]:
        await management.save_profile(project_id,field,text)
    bot.set_my_name.assert_awaited_once_with(name='اسم البوت')
    bot.set_my_description.assert_awaited_once_with(description='وصف')
    bot.set_my_short_description.assert_awaited_once_with(short_description='نبذة')
    assert store.audit.await_count == 3 and bot.session.close.await_count == 3
    with pytest.raises(ValueError):
        await management.save_profile(project_id,'name','x'*65)
    store.session.get.return_value = None
    with pytest.raises(InlineBotError):
        await management.save_profile(project_id,'name','new')
    assert bot.session.close.await_count == 3
