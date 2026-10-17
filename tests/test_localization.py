from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from qmrsmithbot.api.app import app
from qmrsmithbot.api.dependencies import get_current_principal
from qmrsmithbot.db.session import get_session
from qmrsmithbot.localization import MESSAGES, resolve_language


@pytest.mark.parametrize('preference,hint,expected', [
    ('en', 'ar', 'en'), ('ar', 'en', 'ar'), (None, 'en-US', 'en'),
    (None, 'ar_IQ', 'ar'), ('fr', 'en', 'en'), (None, None, 'ar'),
    ('', 'de', 'ar'), (' EN ', None, 'en'),
])
def test_resolution(preference, hint, expected):
    assert resolve_language(preference, hint) == expected


def test_catalog_parity():
    assert MESSAGES['ar'].keys() == MESSAGES['en'].keys()
    assert all(MESSAGES[code].values() for code in MESSAGES)


@pytest.fixture
def client():
    users = {1: SimpleNamespace(language_code=None), 2: SimpleNamespace(language_code='ar')}
    session = AsyncMock()
    session.get.side_effect = lambda model, uid: users.get(uid)
    app.dependency_overrides[get_current_principal] = lambda: SimpleNamespace(user_id=1)
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as c:
        yield c, users
    app.dependency_overrides.clear()


def test_preference_persists_for_current_account_only(client):
    c, users = client
    assert c.get('/api/v1/me/preferences').json()['direction'] == 'rtl'
    assert c.put('/api/v1/me/preferences', json={'language_code': 'en'}).status_code == 200
    assert c.get('/api/v1/me/preferences').json() == {'language_code': 'en', 'direction': 'ltr'}
    assert users[2].language_code == 'ar'


def test_invalid_and_foreign_account_fields_rejected(client):
    c, users = client
    for payload in ({'language_code': 'fr'}, {'language_code': 'en', 'user_id': 2}):
        assert c.put('/api/v1/me/preferences', json=payload).status_code == 422
    assert users[1].language_code is None


def test_missing_account(client):
    c, users = client
    del users[1]
    assert c.get('/api/v1/me/preferences').status_code == 401


def test_language_metadata_and_messages(client):
    c, _ = client
    assert len(c.get('/api/v1/languages').json()) == 2
    assert c.get('/api/v1/languages/ar/messages').json()['my_bots'] == 'بوتاتي'
    assert c.get('/api/v1/languages/fr/messages').status_code == 422


def test_authentication_required():
    with TestClient(app) as c:
        assert c.get('/api/v1/me/preferences').status_code == 401
