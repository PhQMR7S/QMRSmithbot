import importlib.util
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def ingress(monkeypatch):
    monkeypatch.setenv('TELEGRAM_FACTORY_WEBHOOK_SECRET', 'S'*40)
    monkeypatch.setenv('FACTORY_PROTECTION_BYPASS', 'B'*32)
    monkeypatch.setenv('FACTORY_ORIGIN', 'https://private-factory.vercel.app')
    path = Path(__file__).resolve().parents[1] / 'gateways/telegram-ingress/app.py'
    spec = importlib.util.spec_from_file_location('telegram_ingress', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_ingress_rejects_untrusted_requests_before_forwarding(ingress):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ingress.app),
                                 base_url='https://ingress.test') as client:
        assert (await client.post('/webhook', json={'update_id': 1})).status_code == 401
        headers = {'X-Telegram-Bot-Api-Secret-Token': 'S'*40}
        assert (await client.get('/webhook')).status_code == 405
        assert (await client.post('/webhook?key=secret', json={'update_id': 1}, headers=headers)).status_code == 400
        assert (await client.post('/webhook', json={'update_id': True}, headers=headers)).status_code == 400
        assert (await client.post('/webhook', content=b'x'*(ingress.MAX_BODY+1), headers=headers)).status_code == 413
        assert (await client.get('/docs')).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [200, 204, 302, 500])
async def test_ingress_keeps_credentials_in_headers_and_does_not_redirect(ingress, status):
    seen = []
    class Client:
        async def post(self, url, **kwargs):
            seen.append((url, kwargs))
            return httpx.Response(status, json={'method': 'sendMessage', 'chat_id': 1, 'text': 'Hi'})
    async def client_override():
        yield Client()
    ingress.app.dependency_overrides[ingress.upstream_client] = client_override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ingress.app),
                                 base_url='https://ingress.test') as client:
        result = await client.post('/webhook', json={'update_id': 1},
            headers={'X-Telegram-Bot-Api-Secret-Token': 'S'*40})
    assert result.status_code == (status if status in (200, 204) else 503)
    assert seen[0][0] == 'https://private-factory.vercel.app/api/v1/factory/webhook'
    assert seen[0][1]['headers']['x-vercel-protection-bypass'] == 'B'*32
    assert 'B'*32 not in result.text and 'S'*40 not in result.text
    assert '?' not in seen[0][0]
    assert result.headers['cache-control'] == 'no-store'


@pytest.mark.asyncio
async def test_ingress_fails_closed_when_configuration_is_missing(ingress, monkeypatch):
    monkeypatch.delenv('FACTORY_PROTECTION_BYPASS')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ingress.app),
                                 base_url='https://ingress.test') as client:
        assert (await client.post('/webhook', json={'update_id': 1})).status_code == 503


@pytest.mark.asyncio
async def test_child_ingress_isolates_secrets_and_upstream_paths(ingress):
    import hashlib
    import hmac
    from uuid import uuid4
    project_id = uuid4()
    secret = hmac.new(('S'*40).encode(), ('child:' + str(project_id)).encode(), hashlib.sha256).hexdigest()
    seen = []
    class Client:
        async def post(self, url, **kwargs):
            seen.append((url, kwargs))
            return httpx.Response(200, json={'method': 'sendMessage', 'chat_id': 1, 'text': 'Hi'})
    async def client_override():
        yield Client()
    ingress.app.dependency_overrides[ingress.upstream_client] = client_override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ingress.app), base_url='https://ingress.test') as client:
        path = '/bots/' + str(project_id)
        assert (await client.post(path, json={'update_id': 1}, headers={'X-Telegram-Bot-Api-Secret-Token': 'S'*40})).status_code == 401
        headers = {'X-Telegram-Bot-Api-Secret-Token': secret}
        assert (await client.post('/bots/' + str(uuid4()), json={'update_id': 1}, headers=headers)).status_code == 401
        assert (await client.post(path, json={'update_id': 1}, headers=headers)).status_code == 200
    assert len(seen) == 1
    assert seen[0][0] == 'https://private-factory.vercel.app/api/v1/telegram/inline/' + str(project_id)
    assert seen[0][1]['headers']['X-Telegram-Bot-Api-Secret-Token'] == secret


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['sendMessage', 'editMessageText', 'sendRichMessage'])
async def test_ingress_preserves_supported_native_panel_commands(ingress, method):
    payload = {'method': method, 'chat_id': 42, 'reply_markup': {'inline_keyboard': []}}
    if method == 'sendRichMessage':
        payload['rich_message'] = {'html': '<h2>Panel</h2>'}
    else:
        payload['text'] = 'Panel'
    if method == 'editMessageText':
        payload['message_id'] = 17
    class Client:
        async def post(self, *args, **kwargs):
            return httpx.Response(200, json=payload)
    async def override():
        yield Client()
    ingress.app.dependency_overrides[ingress.upstream_client] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ingress.app), base_url='https://test') as client:
        result = await client.post('/webhook', json={'update_id': 7}, headers={'X-Telegram-Bot-Api-Secret-Token': 'S'*40})
        assert result.status_code == 200 and result.json() == payload


@pytest.mark.asyncio
async def test_ingress_reuses_and_closes_lifespan_connection_pool(ingress):
    async with ingress.app.router.lifespan_context(ingress.app):
        first = ingress.upstream_client()
        second = ingress.upstream_client()
        client = await anext(first)
        assert await anext(second) is client
        assert not client.is_closed
        await first.aclose()
        await second.aclose()
        assert not client.is_closed
    assert client.is_closed
    assert not hasattr(ingress.app.state, 'upstream')
