"""Opt-in PostgreSQL tests; use a disposable database with all migrations applied."""
import asyncio
import hashlib
import os
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from aiogram.types import Update
from pydantic import SecretStr
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from qmrsmithbot.auth.telegram_login import TelegramLoginError, TelegramLoginService, digest
from qmrsmithbot.config import settings
from qmrsmithbot.db.factory_models import FactoryUpdateRecord, TelegramLoginChallengeRecord
from qmrsmithbot.db.models import AuditEvent, BotProjectRecord, IdentityRecord, User
from qmrsmithbot.factory.processor import FactoryProcessor
from qmrsmithbot.rate_limit import PostgresRateLimiter

pytestmark = pytest.mark.skipif(
    not os.getenv('QMRSMITH_INTEGRATION_DATABASE_URL'), reason='PostgreSQL integration is opt-in')


@pytest_asyncio.fixture
async def factory_database(monkeypatch):
    engine = create_async_engine(os.environ['QMRSMITH_INTEGRATION_DATABASE_URL'])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    actor_id = int(uuid4().hex[:12], 16) + 10**12
    bot_id = int(uuid4().hex[:10], 16) + 10**9
    monkeypatch.setattr(settings, 'telegram_factory_bot_token', SecretStr(f'{bot_id}:integration'))
    processor = FactoryProcessor(sessions)
    update_id = 0

    def update(text=None, callback=None):
        nonlocal update_id
        update_id += 1
        actor = {'id': actor_id, 'is_bot': False, 'first_name': 'Integration', 'language_code': 'ar'}
        message = {'message_id': update_id, 'date': 1792230000,
                   'chat': {'id': actor_id, 'type': 'private'}, 'from': actor}
        payload = {'update_id': update_id}
        if callback:
            payload['callback_query'] = {'id': str(update_id), 'from': actor,
                'chat_instance': 'integration', 'message': {**message, 'text': 'menu'},
                'data': callback}
        else:
            payload['message'] = {**message, 'text': text}
        return Update.model_validate(payload)

    try:
        yield processor, sessions, update, actor_id, bot_id
    finally:
        # Only records belonging to this randomly generated test identity are removed.
        async with sessions() as session, session.begin():
            user_id = await session.scalar(select(IdentityRecord.user_id).where(
                IdentityRecord.provider == 'telegram', IdentityRecord.subject == str(actor_id)))
            if user_id:
                await session.execute(delete(AuditEvent).where(AuditEvent.actor_user_id == user_id))
                await session.execute(delete(User).where(User.id == user_id))
            await session.execute(delete(FactoryUpdateRecord).where(
                FactoryUpdateRecord.bot_id == bot_id))
            await session.execute(delete(TelegramLoginChallengeRecord).where(
                TelegramLoginChallengeRecord.bot_id == bot_id))
        await engine.dispose()


@pytest.mark.asyncio
async def test_factory_commits_identity_language_and_deduplicates_concurrent_delivery(factory_database):
    processor, sessions, update, actor_id, bot_id = factory_database
    start = update(text='/start')
    results = await asyncio.gather(processor.process(start), processor.process(start))
    assert sum(result is not None for result in results) == 1
    assert next(result for result in results if result)['chat_id'] == actor_id
    await processor.process(update(callback='lang:en'))
    async with sessions() as session:
        user = await session.scalar(select(User).join(IdentityRecord).where(
            IdentityRecord.provider == 'telegram', IdentityRecord.subject == str(actor_id)))
        assert user.id != actor_id
        assert user.language_code == 'en'
        markers = (await session.scalars(select(FactoryUpdateRecord).where(
            FactoryUpdateRecord.bot_id == bot_id))).all()
        assert len(markers) == 2


@pytest.mark.asyncio
async def test_factory_wizard_creates_one_draft_with_real_constraints(factory_database):
    processor, sessions, update, actor_id, _ = factory_database
    await processor.process(update(text='/start'))
    await processor.process(update(callback='template:welcome'))
    await processor.process(update(text='Integration draft'))
    review = await processor.process(update(text='Welcome to the integration test'))
    confirm = review['reply_markup']['inline_keyboard'][0][0]['callback_data']
    confirmation = update(callback=confirm)
    await processor.process(confirmation)
    assert await processor.process(confirmation) is None
    await processor.process(update(callback=confirm))  # A stale button with a fresh update ID.
    async with sessions() as session:
        user_id = await session.scalar(select(IdentityRecord.user_id).where(
            IdentityRecord.provider == 'telegram', IdentityRecord.subject == str(actor_id)))
        projects = (await session.scalars(select(BotProjectRecord).where(
            BotProjectRecord.owner_id == user_id))).all()
        assert len(projects) == 1
        assert projects[0].name == 'Integration draft'
        assert projects[0].status == 'draft'


@pytest.mark.asyncio
async def test_postgres_rate_limit_is_atomic_across_concurrent_sessions(factory_database):
    _, sessions, _, _, _ = factory_database
    limiter = PostgresRateLimiter(sessions)
    key = 'integration:' + uuid4().hex
    digest = hashlib.sha256(key.encode()).hexdigest()
    try:
        results = await asyncio.gather(*(
            limiter.check(key=key, limit=7, window_seconds=60) for _ in range(20)))
        assert sum(result.allowed for result in results) == 7
        async with sessions() as session, session.begin():
            count = await session.scalar(text(
                'SELECT count FROM security_rate_limits WHERE key=:key'), {'key': digest})
            assert count == 7
            await session.execute(text('UPDATE security_rate_limits '
                "SET expires_at=statement_timestamp()-interval '1 second' WHERE key=:key"),
                {'key': digest})
        decision = await limiter.check(key=key, limit=7, window_seconds=60)
        assert decision.allowed and decision.count == 1
    finally:
        async with sessions() as session, session.begin():
            await session.execute(text('DELETE FROM security_rate_limits WHERE key=:key'),
                                  {'key': digest})


@pytest.mark.asyncio
@pytest.mark.parametrize('wrong_count', [0, 4])
async def test_telegram_login_requires_browser_secret_and_consumes_once(factory_database, monkeypatch, wrong_count):
    processor, sessions, update, actor_id, _ = factory_database
    monkeypatch.setattr(settings, 'auth_telegram_enabled', True)
    monkeypatch.setattr(settings, 'telegram_factory_username', 'qmrsmith_test_bot')
    async with sessions() as session, session.begin():
        challenge = await TelegramLoginService(session).begin()
    assert challenge['verification_code'] not in challenge['telegram_url']
    async with sessions() as session, session.begin():
        assert await TelegramLoginService(session).finish(
            challenge['challenge_id'], challenge['browser_secret']) is None
    response = await processor.process(update(text='/start login_' + challenge['challenge_id']))
    assert '🔐' in response['text']
    async with sessions() as session, session.begin():
        with pytest.raises(TelegramLoginError):
            await TelegramLoginService(session).bind(challenge['challenge_id'], actor_id + 1)
    wrong = '000000' if challenge['verification_code'] != '000000' else '111111'
    for _ in range(wrong_count):
        await processor.process(update(text=wrong))
    response = await processor.process(update(text=challenge['verification_code']))
    assert '✅' in response['text']
    async with sessions() as session, session.begin():
        with pytest.raises(TelegramLoginError):
            await TelegramLoginService(session).finish(challenge['challenge_id'], 'wrong-browser')
        record = await session.get(TelegramLoginChallengeRecord, challenge['challenge_id'])
        assert record.browser_secret_hash == digest(challenge['browser_secret'])
        assert record.code_hash != challenge['verification_code']
    async def finish():
        async with sessions() as session, session.begin():
            try:
                return await TelegramLoginService(session).finish(
                    challenge['challenge_id'], challenge['browser_secret'])
            except TelegramLoginError:
                return None
    results = await asyncio.gather(finish(), finish())
    assert sum(result is not None for result in results) == 1
    result = next(result for result in results if result)
    from qmrsmithbot.auth.service import SessionService
    async with sessions() as session, session.begin():
        principal = await SessionService(session).authenticate(result['access_token'])
        identity_user_id = await session.scalar(select(IdentityRecord.user_id).where(
            IdentityRecord.provider == 'telegram', IdentityRecord.subject == str(actor_id)))
        assert principal.user_id == identity_user_id


@pytest.mark.asyncio
async def test_telegram_login_locks_after_five_wrong_codes_and_rejects_expiry(factory_database, monkeypatch):
    processor, sessions, update, actor_id, _ = factory_database
    monkeypatch.setattr(settings, 'auth_telegram_enabled', True)
    monkeypatch.setattr(settings, 'telegram_factory_username', 'qmrsmith_test_bot')
    async with sessions() as session, session.begin():
        challenge = await TelegramLoginService(session).begin()
    await processor.process(update(text='/start login_' + challenge['challenge_id']))
    wrong = '000000' if challenge['verification_code'] != '000000' else '111111'
    for _ in range(5):
        await processor.process(update(text=wrong))
    await processor.process(update(text=challenge['verification_code']))
    async with sessions() as session, session.begin():
        record = await session.get(TelegramLoginChallengeRecord, challenge['challenge_id'])
        assert record.attempts == 5 and record.approved_user_id is None
        with pytest.raises(TelegramLoginError):
            await TelegramLoginService(session).finish(challenge['challenge_id'], challenge['browser_secret'])
        expired = await TelegramLoginService(session).begin()
        await session.execute(text('UPDATE telegram_login_challenges SET '
            "expires_at=statement_timestamp()-interval '1 second' WHERE id=:id"),
            {'id': expired['challenge_id']})
    async with sessions() as session, session.begin():
        with pytest.raises(TelegramLoginError):
            await TelegramLoginService(session).bind(expired['challenge_id'], actor_id)


@pytest.mark.asyncio
async def test_browser_can_cancel_before_telegram_approval(factory_database, monkeypatch):
    _, sessions, _, actor_id, _ = factory_database
    monkeypatch.setattr(settings, 'auth_telegram_enabled', True)
    monkeypatch.setattr(settings, 'telegram_factory_username', 'qmrsmith_test_bot')
    async with sessions() as session, session.begin():
        challenge = await TelegramLoginService(session).begin()
    async with sessions() as session, session.begin():
        await TelegramLoginService(session).cancel(challenge['challenge_id'], challenge['browser_secret'])
    async with sessions() as session, session.begin():
        with pytest.raises(TelegramLoginError):
            await TelegramLoginService(session).bind(challenge['challenge_id'], actor_id)


@pytest.mark.asyncio
async def test_telegram_login_http_to_session_and_logout(factory_database, monkeypatch):
    from qmrsmithbot.api.app import app
    from qmrsmithbot.db.session import get_session
    processor, sessions, update, _, _ = factory_database
    monkeypatch.setattr(settings, 'auth_telegram_enabled', True)
    monkeypatch.setattr(settings, 'telegram_factory_username', 'qmrsmith_test_bot')
    monkeypatch.setattr(settings, 'rate_limit_enabled', False)
    async def session_override():
        async with sessions() as session, session.begin():
            yield session
    app.dependency_overrides[get_session] = session_override
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
            started = await client.post('/api/v1/auth/telegram/start')
            assert started.status_code == 200 and started.headers['cache-control'] == 'no-store'
            challenge = started.json()
            body = {key: challenge[key] for key in ('challenge_id', 'browser_secret')}
            assert (await client.post('/api/v1/auth/telegram/finish', json=body)).status_code == 202
            await processor.process(update(text='/start login_' + challenge['challenge_id']))
            await processor.process(update(text=challenge['verification_code']))
            finished = await client.post('/api/v1/auth/telegram/finish', json=body)
            assert finished.status_code == 200 and finished.headers['cache-control'] == 'no-store'
            headers = {'Authorization': 'Bearer ' + finished.json()['access_token']}
            assert (await client.get('/api/v1/auth/me', headers=headers)).status_code == 200
            assert (await client.post('/api/v1/auth/telegram/finish', json=body)).status_code == 401
            assert (await client.post('/api/v1/auth/logout', headers=headers)).status_code == 204
            assert (await client.get('/api/v1/auth/me', headers=headers)).status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_text_bot_full_lifecycle(factory_database, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import UUID

    from cryptography.fernet import Fernet

    from qmrsmithbot.db.factory_models import FactoryConversationRecord, TelegramInlineBotRecord
    from qmrsmithbot.db.models import BotCredentialRecord
    from qmrsmithbot.telegram.inline_runtime import process_inline_update

    processor, sessions, update, _, _ = factory_database
    monkeypatch.setattr(settings, 'telegram_inline_runtime_enabled', True)
    monkeypatch.setattr(settings, 'telegram_ingress_base_url', 'https://ingress.example')
    monkeypatch.setattr(settings, 'telegram_factory_webhook_secret', SecretStr('S'*40))
    monkeypatch.setattr(settings, 'telegram_credential_encryption_key', SecretStr(Fernet.generate_key().decode()))
    child_id = int(uuid4().hex[:10], 16) + 100000
    child_token = f'{child_id}:' + 'T'*35
    fake = SimpleNamespace(session=SimpleNamespace(close=AsyncMock()),
        get_me=AsyncMock(return_value=SimpleNamespace(id=child_id, username='child_test_bot', is_bot=True)),
        set_webhook=AsyncMock(return_value=True))
    async def webhook_info():
        return SimpleNamespace(url=fake.set_webhook.call_args.kwargs['url'])
    fake.get_webhook_info = webhook_info
    monkeypatch.setattr('qmrsmithbot.factory.bot_management.make_bot', lambda token: fake)
    await processor.process(update(callback='template:welcome'))
    await processor.process(update(text='Lifecycle bot'))
    review = await processor.process(update(text='First greeting'))
    created = await processor.process(update(callback=review['reply_markup']['inline_keyboard'][0][0]['callback_data']))
    panel = created['reply_markup']['inline_keyboard'][0][0]['callback_data']
    project_id = UUID(panel.split(':')[1])
    await processor.process(update(callback='bind:' + str(project_id)))
    connected = await processor.process(update(text=child_token))
    assert 'child_test_bot' in connected['text']
    async with sessions() as session:
        credential = await session.get(BotCredentialRecord, project_id)
        assert child_token not in credential.token_ciphertext
        project = await session.get(BotProjectRecord, project_id)
        conversation = await session.get(FactoryConversationRecord, project.owner_id)
        assert child_token not in str(conversation.data)
    async def launch():
        confirm = await processor.process(update(callback='launchask:' + str(project_id)))
        return await processor.process(update(callback=confirm['reply_markup']['inline_keyboard'][0][0]['callback_data']))
    assert '✅' in (await launch())['text']
    assert fake.set_webhook.call_args.kwargs['allowed_updates'] == ['message', 'callback_query']
    async def reply(event):
        async with sessions() as session, session.begin():
            return await process_inline_update(session, project_id, event)
    first = update(text='/start')
    assert (await reply(first))['text'] == 'First greeting'
    assert await reply(first) == await reply(first)
    await processor.process(update(callback='welcome:' + str(project_id)))
    await processor.process(update(text='Second greeting'))
    assert (await reply(update(text='/start')))['text'] == 'First greeting'
    assert '✅' in (await launch())['text']
    assert (await reply(update(text='/start')))['text'] == 'Second greeting'
    confirm = await processor.process(update(callback='stopask:' + str(project_id)))
    await processor.process(update(callback=confirm['reply_markup']['inline_keyboard'][0][0]['callback_data']))
    assert await reply(update(text='/start')) is None
    confirm = await processor.process(update(callback='resumeask:' + str(project_id)))
    await processor.process(update(callback=confirm['reply_markup']['inline_keyboard'][0][0]['callback_data']))
    assert (await reply(update(text='/start')))['text'] == 'Second greeting'
    async with sessions() as session:
        assert (await session.get(TelegramInlineBotRecord, project_id)).enabled

    # The authenticated HTTP transport serves the same published version.
    from qmrsmithbot.api.app import app
    from qmrsmithbot.db.session import get_session
    from qmrsmithbot.telegram.inline_runtime import child_webhook_secret
    async def session_override():
        async with sessions() as session, session.begin():
            yield session
    app.dependency_overrides[get_session] = session_override
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
            path = '/api/v1/telegram/inline/' + str(project_id)
            body = update(text='/start').model_dump(mode='json', exclude_none=True)
            assert (await client.post(path, json=body)).status_code == 401
            result = await client.post(path, json=body, headers={
                'X-Telegram-Bot-Api-Secret-Token': child_webhook_secret(project_id)})
            assert result.status_code == 200 and result.json()['text'] == 'Second greeting'
    finally:
        app.dependency_overrides.pop(get_session, None)
    # Telegram activation failure must not publish a new draft.
    await processor.process(update(callback='welcome:' + str(project_id)))
    await processor.process(update(text='Must remain a draft'))
    fake.set_webhook.side_effect = TimeoutError()
    assert 'تعذر' in (await launch())['text']
    assert (await reply(update(text='/start')))['text'] == 'Second greeting'


@pytest.mark.asyncio
async def test_modern_editor_preferences_and_stale_buttons(factory_database):
    from uuid import UUID

    from qmrsmithbot.db.models import WorkflowVersionRecord
    from qmrsmithbot.telegram.inline_runtime import compile_text_program

    processor, sessions, update, _, _ = factory_database
    await processor.process(update(callback='template:welcome'))
    await processor.process(update(text='Modern bot'))
    review = await processor.process(update(text='Hello'))
    created = await processor.process(update(callback=review['reply_markup']['inline_keyboard'][0][0]['callback_data']))
    project_id = UUID(created['reply_markup']['inline_keyboard'][0][0]['callback_data'].split(':')[1])
    await processor.process(update(callback='ui:list'))
    await processor.process(update(text='/start'))
    library = await processor.process(update(callback='projects:0'))
    assert 'اختر بوتًا' in library['text']
    callback = update(callback='appearance').model_dump(mode='json', exclude_none=True, by_alias=True)
    callback['callback_query']['message']['from'] = {'id': factory_database[4], 'is_bot': True, 'first_name': 'Factory'}
    assert (await processor.process(Update.model_validate(callback)))['method'] == 'editMessageText'
    await processor.process(update(callback=f'ra:{project_id}:m'))
    await processor.process(update(text='السعر'))
    await processor.process(update(text='10 dollars'))
    await processor.process(update(callback=f'ra:{project_id}:c'))
    await processor.process(update(text='/help'))  # Reserved navigation; must not create a reply.
    await processor.process(update(text='support'))
    content = await processor.process(update(text='Contact admin'))
    entries = [b['callback_data'] for row in content['reply_markup']['inline_keyboard'] for b in row if b.get('callback_data', '').startswith('ri:')]
    assert len(entries) == 2
    old_button = entries[0]
    item = await processor.process(update(callback=old_button))
    edit = item['reply_markup']['inline_keyboard'][0][0]['callback_data']
    await processor.process(update(callback=edit))
    await processor.process(update(text='Updated price'))
    stale = await processor.process(update(callback=old_button))
    assert 'تغيّر' in stale['text']
    content = await processor.process(update(callback=f'content:{project_id}'))
    button = next(b['callback_data'] for row in content['reply_markup']['inline_keyboard'] for b in row if b.get('callback_data', '').startswith('ri:'))
    item = await processor.process(update(callback=button))
    delete_button = item['reply_markup']['inline_keyboard'][0][1]['callback_data']
    confirm = await processor.process(update(callback=delete_button))
    confirmation = confirm['reply_markup']['inline_keyboard'][0][0]['callback_data']
    await processor.process(update(callback=confirmation))
    await processor.process(update(callback=confirmation))  # Single-use deletion.
    async with sessions() as session:
        latest = await session.scalar(select(WorkflowVersionRecord).where(WorkflowVersionRecord.project_id == project_id).order_by(WorkflowVersionRecord.version.desc()).limit(1))
        program = compile_text_program(latest.definition)
        assert program.messages == {} and program.commands == {'start': 'Hello', 'support': 'Contact admin'}
    await processor.process(update(callback=f'simulate:{project_id}'))
    assert 'Contact admin' in (await processor.process(update(text='/support')))['text']
    await processor.process(update(text='/cancel'))
    # A second identity cannot read or mutate the first identity's content.
    other = update(callback=f'ra:{project_id}:m').model_dump(mode='json', exclude_none=True, by_alias=True)
    actor = other['callback_query']['from']
    actor['id'] += 123456
    other['callback_query']['message']['chat']['id'] = actor['id']
    try:
        result = await processor.process(Update.model_validate(other))
        assert 'غير متاح' in result['text']
    finally:
        async with sessions() as session, session.begin():
            other_id = await session.scalar(select(IdentityRecord.user_id).where(
                IdentityRecord.provider == 'telegram', IdentityRecord.subject == str(actor['id'])))
            if other_id:
                await session.execute(delete(AuditEvent).where(AuditEvent.actor_user_id == other_id))
                await session.execute(delete(User).where(User.id == other_id))


async def create_product_bot(factory_database, monkeypatch, kind):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import UUID

    from cryptography.fernet import Fernet
    processor, sessions, update, actor_id, _ = factory_database
    monkeypatch.setattr(settings,'telegram_inline_runtime_enabled',True)
    monkeypatch.setattr(settings,'telegram_ingress_base_url','https://ingress.example')
    monkeypatch.setattr(settings,'telegram_factory_webhook_secret',SecretStr('S'*40))
    monkeypatch.setattr(settings,'telegram_credential_encryption_key',SecretStr(Fernet.generate_key().decode()))
    child_id = int(uuid4().hex[:10],16)+100000
    fake = SimpleNamespace(session=SimpleNamespace(close=AsyncMock()),
        get_me=AsyncMock(return_value=SimpleNamespace(id=child_id,username='product_test_bot',is_bot=True)),
        set_webhook=AsyncMock(return_value=True))
    async def info():
        return SimpleNamespace(url=fake.set_webhook.call_args.kwargs['url'])
    fake.get_webhook_info=info
    monkeypatch.setattr('qmrsmithbot.factory.bot_management.make_bot',lambda token:fake)
    await processor.process(update(callback='template:'+kind))
    await processor.process(update(text=kind+' bot'))
    review=await processor.process(update(text='Product welcome'))
    created=await processor.process(update(callback=review['reply_markup']['inline_keyboard'][0][0]['callback_data']))
    project_id=UUID(created['reply_markup']['inline_keyboard'][0][0]['callback_data'].split(':')[1])
    await processor.process(update(callback='bind:'+str(project_id)))
    await processor.process(update(text=f'{child_id}:'+ 'T'*35))
    async def launch():
        ask=await processor.process(update(callback='launchask:'+str(project_id)))
        result=await processor.process(update(callback=ask['reply_markup']['inline_keyboard'][0][0]['callback_data']))
        assert '✅' in result['text'], result['text']
    async def deliver(*, text=None, callback=None, actor=None, document=None, reply_to=None):
        from qmrsmithbot.telegram.inline_runtime import process_inline_update
        event=update(text=text or 'media',callback=callback).model_dump(mode='json',exclude_none=True,by_alias=True)
        person={'id':actor or actor_id,'is_bot':False,'first_name':'Visitor'}
        message=event['callback_query']['message'] if callback else event['message']
        message['chat']['id']=person['id']
        message['from']=person
        if callback:
            event['callback_query']['from']=person
            message['from']={'id':child_id,'is_bot':True,'first_name':'Bot'}
        if document:
            message.pop('text',None)
            message['document']={'file_id':document,'file_unique_id':'unique','file_size':999999999}
        if reply_to:
            message['reply_to_message']={'message_id':reply_to,'date':1792230000,
                'chat':{'id':person['id'],'type':'private'},'from':{'id':child_id,'is_bot':True,'first_name':'Bot'},'text':'Incoming'}
        parsed=Update.model_validate(event)
        async with sessions() as session, session.begin():
            response=await process_inline_update(session,project_id,parsed)
        return response, parsed
    return project_id, child_id, launch, deliver


@pytest.mark.asyncio
async def test_button_bot_nested_drafts_files_publication_and_isolation(factory_database,monkeypatch):
    from qmrsmithbot.db.factory_models import FactoryButtonRecord
    from qmrsmithbot.telegram.inline_runtime import process_inline_update
    processor,sessions,update,owner,_=factory_database
    project_id,_,launch,deliver=await create_product_bot(factory_database,monkeypatch,'buttons')
    await launch()
    await processor.process(update(callback=f'bnew:{project_id.hex}:r:section'))
    await processor.process(update(text='Courses'))
    async with sessions() as session:
        section=await session.scalar(select(FactoryButtonRecord).where(FactoryButtonRecord.project_id==project_id))
        section_id=section.id
    await processor.process(update(callback=f'bnew:{section_id.hex}:p:text'))
    await processor.process(update(text='About'))
    await processor.process(update(text='Detailed content'))
    before,_=await deliver(text='/start',actor=owner+1)
    assert 'Courses' not in str(before)
    await launch()
    root,_=await deliver(text='/start',actor=owner+1)
    assert root['reply_markup']['inline_keyboard'][0][0]['text']=='Courses'
    nested,_=await deliver(callback='b:'+section_id.hex,actor=owner+1)
    assert nested['method']=='editMessageText' and 'About' in str(nested)
    item_data=nested['reply_markup']['inline_keyboard'][0][0]['callback_data']
    content,_=await deliver(callback=item_data,actor=owner+1)
    assert content['text']=='Detailed content'
    await processor.process(update(callback=f'bnew:{project_id.hex}:r:file'))
    await processor.process(update(text='Lecture PDF'))
    async with sessions() as session:
        file=await session.scalar(select(FactoryButtonRecord).where(FactoryButtonRecord.project_id==project_id,
            FactoryButtonRecord.draft['kind'].astext=='file'))
        file_id=file.id
    await deliver(text='/start upload_'+file_id.hex,actor=owner+1)
    await deliver(document='visitor-file',actor=owner+1)
    async with sessions() as session:
        assert 'file_id' not in (await session.get(FactoryButtonRecord,file_id)).draft
    await deliver(text='/start upload_'+file_id.hex)
    received,event=await deliver(document='child-file-reference')
    assert 'استلمت' in received['text']
    # Same incoming file update is cached and cannot be re-applied.
    async with sessions() as session, session.begin():
        assert await process_inline_update(session,project_id,event)==received
    await launch()
    file_response,_=await deliver(callback='b:'+file_id.hex,actor=owner+1)
    assert file_response['method']=='sendDocument' and file_response['document']=='child-file-reference'
    ask=await processor.process(update(callback='bdel:'+section_id.hex))
    await processor.process(update(callback=ask['reply_markup']['inline_keyboard'][0][0]['callback_data']))
    assert (await deliver(callback=item_data,actor=owner+1))[0]['text']=='Detailed content'
    await launch()
    assert 'غير متاح' in (await deliver(callback=item_data,actor=owner+1))[0]['text']
    assert (await deliver(callback='b:'+uuid4().hex,actor=owner+1))[0]['text'].startswith('هذا الزر غير متاح')


@pytest.mark.asyncio
async def test_contact_bot_routes_only_owner_replies_blocks_and_deduplicates(factory_database,monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from qmrsmithbot.db.factory_models import ContactDeliveryRecord
    from qmrsmithbot.telegram.inline_runtime import process_inline_update
    processor,sessions,update,owner,_=factory_database
    project_id,_,launch,deliver=await create_product_bot(factory_database,monkeypatch,'contact')
    await launch()
    next_id=1000
    async def copy(**kwargs):
        nonlocal next_id
        next_id+=1
        return SimpleNamespace(message_id=next_id)
    fake=SimpleNamespace(copy_message=AsyncMock(side_effect=copy))
    @asynccontextmanager
    async def client(self,project):
        assert project==project_id
        yield fake
    monkeypatch.setattr('qmrsmithbot.telegram.product_runtime.TelegramBotClientFactory.bot',client)
    visitor=owner+1
    result,event=await deliver(text='Question',actor=visitor)
    assert 'وصلت' in result['text']
    assert fake.copy_message.call_args.kwargs['chat_id']==owner
    async with sessions() as session,session.begin():
        assert await process_inline_update(session,project_id,event)==result
        route=await session.get(ContactDeliveryRecord,(project_id,1001))
        assert route.visitor_id==visitor
    assert fake.copy_message.await_count==1
    await deliver(document='owner-answer',reply_to=1001)
    assert fake.copy_message.call_args.kwargs['chat_id']==visitor
    count=fake.copy_message.await_count
    await deliver(text='Unsolicited owner message')
    await deliver(text='Forged reply',reply_to=99999)
    await deliver(callback=f'contact:block:{visitor}',actor=visitor)
    assert fake.copy_message.await_count==count
    assert 'تم الحظر' in (await deliver(callback=f'contact:block:{visitor}'))[0]['text']
    await deliver(text='Blocked',actor=visitor)
    assert fake.copy_message.await_count==count
    await deliver(callback=f'contact:unblock:{visitor}')
    await deliver(document='visitor-attachment',actor=visitor)
    assert fake.copy_message.await_count==count+1
    # Stop makes all messages inert, including owner replies.
    ask=await processor.process(update(callback='stopask:'+str(project_id)))
    await processor.process(update(callback=ask['reply_markup']['inline_keyboard'][0][0]['callback_data']))
    assert (await deliver(text='Stopped',actor=visitor))[0] is None
    assert fake.copy_message.await_count==count+1


@pytest.mark.asyncio
async def test_native_managed_creation_confirmation_and_duplicate_event(factory_database, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import UUID

    from cryptography.fernet import Fernet

    from qmrsmithbot.db.models import BotCredentialRecord

    processor, sessions, update, actor_id, factory_id = factory_database
    monkeypatch.setattr(settings, 'telegram_inline_runtime_enabled', True)
    monkeypatch.setattr(settings, 'telegram_factory_webhook_secret', SecretStr('S'*40))
    monkeypatch.setattr(settings, 'telegram_credential_encryption_key', SecretStr(Fernet.generate_key().decode()))
    child_id = int(uuid4().hex[:10], 16) + 100000
    child_token = f'{child_id}:' + 'T'*35
    factory = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(
        id=factory_id, username='ManagerBot',can_manage_bots=True)),
        get_managed_bot_token=AsyncMock(return_value=child_token),
        session=SimpleNamespace(close=AsyncMock()))
    child = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(
        id=child_id, username='NativeBot',is_bot=True)),session=SimpleNamespace(close=AsyncMock()))
    monkeypatch.setattr('qmrsmithbot.factory.bot_management.make_bot',
        lambda token: child if token == child_token else factory)
    await processor.process(update(callback='template:welcome'))
    await processor.process(update(text='Native project'))
    review = await processor.process(update(text='Hello'))
    created = await processor.process(update(callback=review['reply_markup']['inline_keyboard'][0][0]['callback_data']))
    project_id = UUID(created['reply_markup']['inline_keyboard'][0][0]['callback_data'].split(':')[1])
    native = await processor.process(update(callback='managed:'+str(project_id)))
    assert native['reply_markup']['inline_keyboard'][0][0]['url'].startswith('https://t.me/newbot/ManagerBot/')
    event = Update.model_validate({'update_id':900001, 'managed_bot': {
        'user':{'id':actor_id,'is_bot':False,'first_name':'Integration'},
        'bot':{'id':child_id,'is_bot':True,'first_name':'Native','username':'NativeBot'}}})
    received = await processor.process(event)
    assert 'NativeBot' in received['text'] and received['chat_id'] == actor_id
    assert await processor.process(event) is None
    async with sessions() as session:
        project = await session.get(BotProjectRecord,project_id)
        assert project.telegram_bot_id == child_id and project.status == 'draft'
        assert await session.get(BotCredentialRecord,project_id) is None
    confirmation = received['reply_markup']['inline_keyboard'][0][0]['callback_data']
    bound = await processor.process(update(callback=confirmation))
    assert '✅' in bound['text']
    async with sessions() as session:
        credential = await session.get(BotCredentialRecord,project_id)
        assert child_token not in credential.token_ciphertext
    factory.get_managed_bot_token.assert_awaited_once_with(user_id=child_id)
    await processor.process(update(callback=confirmation))
    factory.get_managed_bot_token.assert_awaited_once()
