import httpx
import pytest
from pydantic import SecretStr

from qmrsmithbot.api.app import app
from qmrsmithbot.config import Settings, settings
from qmrsmithbot.db.session import get_session


@pytest.mark.asyncio
async def test_telegram_login_is_opt_in_and_payloads_are_bounded(monkeypatch):
    monkeypatch.setattr(settings, 'auth_telegram_enabled', False)
    monkeypatch.setattr(settings, 'rate_limit_enabled', False)
    async def session():
        yield object()
    app.dependency_overrides[get_session] = session
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
            methods = await client.get('/api/v1/auth/methods')
            assert methods.json()['telegram'] is False
            assert methods.headers['cache-control'] == 'no-store'
            result = await client.post('/api/v1/auth/telegram/start')
            assert result.status_code == 404
            assert result.headers['cache-control'] == 'no-store'
            assert (await client.post('/api/v1/auth/telegram/finish', json={
                'challenge_id': 'x'*1000, 'browser_secret': 'x'*1000})).status_code == 422
            assert (await client.get('/api/v1/auth/telegram/start')).status_code == 405
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_telegram_login_configuration_requires_factory_and_username():
    with pytest.raises(ValueError, match='TELEGRAM_FACTORY_ENABLED'):
        Settings(auth_telegram_enabled=True)
    common = {'auth_telegram_enabled': True, 'telegram_factory_enabled': True,
        'telegram_factory_bot_token': SecretStr('123456789:' + 'A'*35),
        'telegram_factory_webhook_secret': SecretStr('S'*32),
        'telegram_webhook_base_url': 'https://example.com'}
    with pytest.raises(ValueError, match='USERNAME'):
        Settings(**common, telegram_factory_username='@wrong')
    valid = Settings(**common, telegram_factory_username='qmrsmith_test_bot')
    assert valid.auth_telegram_enabled
    production = Settings(**common, telegram_factory_username='qmrsmith_test_bot',
        app_env='production', auth_dev_bootstrap_enabled=False, rate_limit_enabled=True,
        rate_limit_backend='postgresql', database_url='postgresql+asyncpg://app:secret@db/qmrsmith',
        telegram_credential_encryption_key=SecretStr('BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB='))
    assert production.auth_telegram_enabled and not production.auth_oidc_enabled
