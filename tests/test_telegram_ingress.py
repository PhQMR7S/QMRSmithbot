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
