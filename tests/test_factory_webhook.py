from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from qmrsmithbot.api.app import app
from qmrsmithbot.api.factory import get_factory_processor
from qmrsmithbot.config import settings

SECRET = 'a' * 48
UPDATE = {'update_id': 1, 'message': {'message_id': 1, 'date': 0,
    'chat': {'id': 42, 'type': 'private'},
    'from': {'id': 42, 'is_bot': False, 'first_name': 'Test'}, 'text': '/start'}}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, 'telegram_factory_enabled', True)
    from pydantic import SecretStr
    monkeypatch.setattr(settings, 'telegram_factory_webhook_secret', SecretStr(SECRET))
    processor = AsyncMock()
    processor.process.return_value = {'method': 'sendMessage', 'chat_id': 42, 'text': 'Menu'}
    app.dependency_overrides[get_factory_processor] = lambda: processor
    with TestClient(app) as c:
        yield c, processor
    app.dependency_overrides.pop(get_factory_processor, None)


def test_secret_required_before_processor(client):
    c, processor = client
    assert c.post('/api/v1/factory/webhook', json=UPDATE).status_code == 401
    processor.process.assert_not_awaited()


def test_valid_webhook_response_and_duplicate(client):
    c, processor = client
    headers = {'X-Telegram-Bot-Api-Secret-Token': SECRET}
    assert c.post('/api/v1/factory/webhook', json=UPDATE, headers=headers).json()['method'] == 'sendMessage'
    processor.process.return_value = None
    assert c.post('/api/v1/factory/webhook', json=UPDATE, headers=headers).status_code == 204


def test_payload_limits_and_validation(client):
    c, processor = client
    headers = {'X-Telegram-Bot-Api-Secret-Token': SECRET}
    assert c.post('/api/v1/factory/webhook', content='{', headers=headers).status_code == 400
    assert c.post('/api/v1/factory/webhook', json=[], headers=headers).status_code == 400
    assert c.post('/api/v1/factory/webhook', content='x' * 1048577, headers=headers).status_code == 413
    processor.process.assert_not_awaited()


def test_factory_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, 'telegram_factory_enabled', False)
    with TestClient(app) as c:
        assert c.post('/api/v1/factory/webhook', json=UPDATE).status_code == 503



def test_negative_update_id_rejected(client):
    c, processor = client
    assert c.post('/api/v1/factory/webhook', json={**UPDATE, 'update_id': -1},
                  headers={'X-Telegram-Bot-Api-Secret-Token': SECRET}).status_code == 400
    processor.process.assert_not_awaited()
