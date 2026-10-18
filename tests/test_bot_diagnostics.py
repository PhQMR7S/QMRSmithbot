from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from qmrsmithbot.auth.models import Permission
from qmrsmithbot.factory.bot_management import BotManagement
from qmrsmithbot.factory.diagnostics import describe_connection


def test_diagnostic_distinguishes_historical_errors_and_api_timing():
    report = describe_connection(language='en', identity_matches=True, webhook_matches=False,
        has_webhook=True, pending=12, last_error=datetime(2026, 1, 1, tzinfo=UTC),
        elapsed_ms=250, running=False)
    assert 'points elsewhere' in report
    assert 'Pending updates: 12' in report
    assert 'may be historical' in report
    assert 'not visitor response time' in report
    assert 'stopped or unpublished' in report


@pytest.mark.asyncio
async def test_check_is_read_only_scoped_and_closes_session(monkeypatch):
    store = SimpleNamespace(session=SimpleNamespace(get=AsyncMock(side_effect=[
        SimpleNamespace(token_ciphertext='encrypted'), SimpleNamespace(enabled=True)])))
    manager = BotManagement(store)
    manager.project = AsyncMock(return_value=SimpleNamespace(telegram_bot_id=42, status='running'))
    bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(id=42)),
        get_webhook_info=AsyncMock(return_value=SimpleNamespace(url='', pending_update_count=0,
            last_error_date=None)), session=SimpleNamespace(close=AsyncMock()))
    monkeypatch.setattr('qmrsmithbot.factory.bot_management.make_bot', lambda token: bot)
    monkeypatch.setattr('qmrsmithbot.factory.bot_management.decrypt_bot_token', lambda value: 'secret')
    project_id = uuid4()
    result = await manager.diagnose(project_id, 'ar')
    manager.project.assert_awaited_once_with(project_id, Permission.PROJECT_WRITE)
    bot.session.close.assert_awaited_once()
    assert 'غير مسجل' in result
    assert 'secret' not in result
    bot.get_me.side_effect = TimeoutError('secret')
    store.session.get.side_effect = [SimpleNamespace(token_ciphertext='encrypted'), None]
    result = await manager.diagnose(project_id, 'en')
    assert 'Check unavailable' in result
    assert 'secret' not in result
    assert bot.session.close.await_count == 2


@pytest.mark.asyncio
async def test_denied_project_never_reads_credentials_or_calls_telegram(monkeypatch):
    session = SimpleNamespace(get=AsyncMock())
    manager = BotManagement(SimpleNamespace(session=session))
    manager.project = AsyncMock(side_effect=PermissionError())
    def forbidden(token):
        raise AssertionError('Telegram must not be contacted')
    monkeypatch.setattr('qmrsmithbot.factory.bot_management.make_bot', forbidden)
    with pytest.raises(PermissionError):
        await manager.diagnose(uuid4(), 'en')
    session.get.assert_not_awaited()
