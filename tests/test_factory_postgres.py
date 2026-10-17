"""Opt-in PostgreSQL tests; use a disposable database with all migrations applied."""
import asyncio
import hashlib
import os
from uuid import uuid4

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
