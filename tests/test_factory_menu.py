from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from aiogram.types import Update

from qmrsmithbot.factory.menu import COPY, FactoryMenu, MenuState
from qmrsmithbot.factory.processor import FactoryProcessor, private_actor
from qmrsmithbot.factory.store import telegram_identity


class Store:
    def __init__(self):
        self.lang = 'ar'
        self.conversation = MenuState('idle', {})
        self.created = []
        self.items = []
        self.changes = []

    async def language(self):
        return self.lang

    async def set_language(self, code):
        self.lang = code

    async def state(self):
        return self.conversation

    async def save_state(self, state):
        self.conversation = state

    async def projects(self, *, offset, limit):
        return self.items[offset:offset + limit]

    async def project(self, project_id):
        return next((p for p in self.items if p.id == project_id), None)

    async def set_running(self, project_id, running):
        self.changes.append((project_id, running))

    async def create(self, name, definition):
        self.created.append((name, definition))


def callback_data(response, row=0, column=0):
    return response['reply_markup']['inline_keyboard'][row][column]['callback_data']


async def test_language_and_private_menu():
    store = Store()
    menu = FactoryMenu(store, telegram_id=42)
    response = await menu.handle(text='/start')
    assert 'مصنع' in response['text']
    assert COPY['ar']['admin'] not in str(response)
    await menu.handle(callback='lang:en')
    assert store.lang == 'en'
    assert 'Bot Factory' in (await menu.handle(text='/start'))['text']
    assert COPY['ar'].keys() == COPY['en'].keys()


@pytest.mark.parametrize('template,rules', [
    ('welcome', None), ('auto-replies', 'السعر | اسأل الإدارة'), ('command-menu', 'help | Help text'),
])
async def test_full_wizard_creates_once(template, rules):
    store = Store()
    menu = FactoryMenu(store, telegram_id=42)
    await menu.handle(callback='template:' + template)
    await menu.handle(text='My bot')
    response = await menu.handle(text='Welcome')
    if rules:
        key, reply = rules.split('|', 1)
        await menu.handle(text=key.strip())
        await menu.handle(text=reply.strip())
        response = await menu.handle(callback='wizarddone')
    confirmation = callback_data(response)
    assert confirmation.startswith('confirm:')
    assert not store.created
    await menu.handle(callback=confirmation)
    await menu.handle(callback=confirmation)
    assert len(store.created) == 1
    assert store.created[0][0] == 'My bot'
    assert store.conversation.step == 'idle'


async def test_cancel_and_old_confirmation_do_not_create():
    store = Store()
    menu = FactoryMenu(store, telegram_id=42)
    await menu.handle(callback='template:welcome')
    await menu.handle(text='First')
    old = callback_data(await menu.handle(text='Welcome'))
    await menu.handle(text='/cancel')
    await menu.handle(callback='template:welcome')
    await menu.handle(text='Second')
    await menu.handle(text='Hello')
    await menu.handle(callback=old)
    assert not store.created


async def test_rules_validation_and_secret_rejection():
    store = Store()
    menu = FactoryMenu(store, telegram_id=42)
    await menu.handle(callback='template:auto-replies')
    await menu.handle(text='123456:' + 'a' * 35)
    assert store.conversation.step == 'name'
    await menu.handle(text='FAQ')
    await menu.handle(text='Hello')
    await menu.handle(text='word')
    assert store.conversation.step == 'wizard_reply'
    await menu.handle(text='123456:' + 'a'*35)
    assert store.conversation.step == 'wizard_reply'
    await menu.handle(text='Answer')
    await menu.handle(callback='wizardadd')
    await menu.handle(text='word')
    assert store.conversation.step == 'wizard_key'
    assert not store.created



async def test_pagination_and_unknown_project():
    store = Store()
    store.items = [SimpleNamespace(id=uuid4(), name=f'Bot {n}') for n in range(10)]
    menu = FactoryMenu(store, telegram_id=42)
    response = await menu.handle(callback='projects:0')
    assert 'projects:8' in str(response)
    assert 'projects:0' in str(await menu.handle(callback='projects:8'))
    assert COPY['ar']['missing'] == (await menu.handle(callback=f'project:{uuid4()}'))['text']
    assert COPY['ar']['invalid'] == (await menu.handle(callback='projects:-1'))['text']


async def test_lifecycle_confirmation_is_single_use():
    store = Store()
    project = SimpleNamespace(id=uuid4(), name='A', status='running', active_version=1)
    store.items = [project]
    menu = FactoryMenu(store, telegram_id=42)
    response = await menu.handle(callback=f'stopask:{project.id}')
    confirm = callback_data(response)
    assert not store.changes
    await menu.handle(callback=confirm)
    await menu.handle(callback=confirm)
    assert store.changes == [(project.id, False)]


@pytest.mark.parametrize('chat_type,chat_id,actor_bot', [('group', -42, False), ('private', 99, False), ('private', 42, True)])
def test_untrusted_or_group_context_ignored(chat_type, chat_id, actor_bot):
    update = Update.model_validate({'update_id': 1, 'message': {'message_id': 1, 'date': 0,
        'chat': {'id': chat_id, 'type': chat_type}, 'from': {'id': 42, 'is_bot': actor_bot,
        'first_name': 'Test'}, 'text': '/start'}})
    assert private_actor(update) is None


async def test_telegram_identity_does_not_claim_same_numeric_platform_user(monkeypatch):
    session = AsyncMock()
    session.add = MagicMock()
    session.scalar.return_value = None
    session.get.return_value = None
    monkeypatch.setattr('qmrsmithbot.factory.store.secrets.randbelow', lambda n: 88)
    actor = SimpleNamespace(id=42, username=None, first_name='A', language_code='en')
    user = await telegram_identity(session, actor)
    assert user.id == 89
    assert user.id != actor.id
    assert session.add.call_args.args[0].provider == 'telegram'
    assert session.add.call_args.args[0].subject == '42'


async def test_duplicate_update_never_runs_menu(monkeypatch):
    session = AsyncMock()
    session.begin = MagicMock(return_value=AsyncMock())
    session.scalar.return_value = None
    context = AsyncMock()
    context.__aenter__.return_value = session
    store = AsyncMock()
    monkeypatch.setattr('qmrsmithbot.factory.processor.factory_store', store)
    monkeypatch.setattr('qmrsmithbot.factory.processor.settings.telegram_factory_bot_token',
                        SimpleNamespace(get_secret_value=lambda: '123456:fake'))
    update = Update.model_validate({'update_id': 1, 'message': {'message_id': 1, 'date': 0,
        'chat': {'id': 42, 'type': 'private'}, 'from': {'id': 42, 'is_bot': False,
        'first_name': 'Test'}, 'text': '/start'}})
    assert await FactoryProcessor(sessions=lambda: context).process(update) is None
    store.assert_not_awaited()


async def test_appearance_survives_navigation_and_wizard():
    store = Store()
    menu = FactoryMenu(store, telegram_id=42)
    await menu.handle(callback='ui:list')
    await menu.handle(callback='ui:rich')
    await menu.handle(text='/start')
    await menu.handle(callback='template:welcome')
    await menu.handle(text='Name')
    await menu.handle(callback='wizarddefault')
    assert store.conversation.step == 'confirm'
    assert store.conversation.data['_ui'] == {'layout': 'list', 'rich': True}
    await menu.handle(callback='wizard:name')
    review = await menu.handle(text='New name')
    assert 'New name' in review['text'] and store.conversation.step == 'confirm'
    await menu.handle(callback='ui:plain')
    assert store.conversation.data['_ui']['rich'] is False
