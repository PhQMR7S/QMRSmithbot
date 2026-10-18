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


@pytest.mark.asyncio
async def test_dashboard_proxy_is_allowlisted_and_preserves_application_auth(ingress):
    seen=[]
    class Client:
        async def request(self,method,url,**kwargs):
            seen.append((method,url,kwargs))
            return httpx.Response(200,json={'items':[]},headers={'Set-Cookie':'must-not-escape','Location':'https://wrong.example'})
    async def override():
        yield Client()
    ingress.app.dependency_overrides[ingress.upstream_client]=override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ingress.app),base_url='https://test') as client:
        assert (await client.get('/api/v1/projects')).status_code==401
        assert (await client.get('/api/v1/auth/dev/bootstrap',headers={'Authorization':'Bearer sample-session'})).status_code==404
        assert (await client.post('/api/v1/factory/webhook')).status_code==404
        assert (await client.get('/api/v1/projects?token=not-allowed',headers={'Authorization':'Bearer sample-session'})).status_code==400
        assert (await client.post('/api/v1/auth/telegram/start',headers={'Origin':'https://evil.example'})).status_code==403
        result=await client.get('/api/v1/projects?limit=20',headers={
            'Authorization':'Bearer sample-session','X-QMRSmith-Tenant-ID':'tenant','x-vercel-protection-bypass':'attacker'})
    assert result.status_code==200 and result.json()=={'items':[]}
    assert 'set-cookie' not in result.headers and 'location' not in result.headers
    assert len(seen)==1
    _,url,request=seen[0]
    assert url=='https://private-factory.vercel.app/api/v1/projects'
    assert request['headers']['Authorization']=='Bearer sample-session'
    assert request['headers']['X-QMRSmith-Tenant-ID']=='tenant'
    assert request['headers']['x-vercel-protection-bypass']=='B'*32
    assert 'B'*32 not in result.text


@pytest.mark.asyncio
@pytest.mark.parametrize('status,content_type',[(302,'text/html'),(500,'application/json'),(200,'text/html')])
async def test_dashboard_api_never_relays_redirects_or_html_errors(ingress,status,content_type):
    class Client:
        async def request(self,*args,**kwargs):
            return httpx.Response(status,content='sensitive exception',headers={'Content-Type':content_type})
    async def override():
        yield Client()
    ingress.app.dependency_overrides[ingress.upstream_client]=override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ingress.app),base_url='https://test') as client:
        result=await client.get('/api/v1/projects',headers={'Authorization':'Bearer sample-session'})
    assert result.status_code==503 and 'sensitive' not in result.text


@pytest.mark.asyncio
async def test_dashboard_pages_have_strict_asset_paths_and_bounded_bodies(ingress):
    class Client:
        async def request(self,*args,**kwargs):
            return httpx.Response(200,content='<html>Sign in</html>',headers={
                'Content-Type':'text/html','Content-Security-Policy':"default-src 'self'"})
    async def override():
        yield Client()
    ingress.app.dependency_overrides[ingress.upstream_client]=override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ingress.app),base_url='https://test') as client:
        result=await client.get('/dashboard')
        assert result.status_code==200 and result.headers['content-security-policy']=="default-src 'self'"
        assert result.headers['cache-control']=='no-store'
        assert (await client.get('/dashboard/assets/config.py')).status_code==404
        assert (await client.post('/api/v1/auth/telegram/finish',content=b'x'*(ingress.MAX_BODY+1),headers={'Content-Type':'application/json'})).status_code==413
