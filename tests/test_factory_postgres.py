"""Opt-in PostgreSQL tests; use a disposable database with all migrations applied."""
import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from aiogram.types import Update
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from qmrsmithbot.config import settings
from qmrsmithbot.db.factory_models import FactoryUpdateRecord
from qmrsmithbot.db.models import AuditEvent, BotProjectRecord, IdentityRecord, User
from qmrsmithbot.factory.processor import FactoryProcessor

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
