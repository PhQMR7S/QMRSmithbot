"""Bounded public entry for Telegram and authenticated dashboard routes."""
import hashlib
import hmac
import json
import os
import re
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response


@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)) as client:
        app.state.upstream = client
        try:
            yield
        finally:
            del app.state.upstream


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
MAX_BODY = 1_048_576
HEADERS = {'Cache-Control': 'no-store'}


async def upstream_client():
    pooled = getattr(app.state, 'upstream', None)
    if pooled is not None:
        yield pooled
        return
    # ASGI hosts that do not run lifespan still have a bounded, request-scoped fallback.
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
        yield client


@app.get('/health')
async def health():
    return {'status': 'ok', 'service': 'qmrsmithbot-telegram-ingress'}


@app.post('/webhook')
async def webhook(request: Request, client: Annotated[httpx.AsyncClient, Depends(upstream_client)]):
    return await forward(request, client, '/api/v1/factory/webhook',
                         os.environ.get('TELEGRAM_FACTORY_WEBHOOK_SECRET', ''))


@app.post('/bots/{project_id}')
async def child_webhook(project_id: UUID, request: Request,
        client: Annotated[httpx.AsyncClient, Depends(upstream_client)]):
    key = os.environ.get('TELEGRAM_FACTORY_WEBHOOK_SECRET', '')
    if len(key) < 32:
        raise HTTPException(status_code=503, detail='Ingress is unavailable', headers=HEADERS)
    secret = hmac.new(key.encode(), ('child:' + str(project_id)).encode(), hashlib.sha256).hexdigest()
    return await forward(request, client, '/api/v1/telegram/inline/' + str(project_id), secret)


async def forward(request, client, path, secret):
    bypass = os.environ.get('FACTORY_PROTECTION_BYPASS', '')
    origin = os.environ.get('FACTORY_ORIGIN', '').rstrip('/')
    parsed = urlsplit(origin)
    if (len(secret) < 32 or len(bypass) < 20 or parsed.scheme != 'https'
            or not parsed.hostname or not parsed.hostname.endswith('.vercel.app')
            or parsed.username or parsed.password or parsed.port or parsed.path
            or parsed.query or parsed.fragment):
        raise HTTPException(status_code=503, detail='Ingress is unavailable', headers=HEADERS)
    supplied = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if len(supplied) > 256 or not hmac.compare_digest(supplied.encode(), secret.encode()):
        raise HTTPException(status_code=401, detail='Invalid webhook secret', headers=HEADERS)
    if request.url.query:
        raise HTTPException(status_code=400, detail='Query parameters are not accepted', headers=HEADERS)
    declared = request.headers.get('Content-Length')
    if declared is not None:
        try:
            size = int(declared)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail='Invalid content length', headers=HEADERS) from exc
        if size < 0 or size > MAX_BODY:
            raise HTTPException(status_code=413, detail='Payload is too large', headers=HEADERS)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY:
            raise HTTPException(status_code=413, detail='Payload is too large', headers=HEADERS)
        body.extend(chunk)
    try:
        payload = json.loads(body)
        if (not isinstance(payload, dict) or type(payload.get('update_id')) is not int
                or payload['update_id'] < 0):
            raise ValueError()
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail='Invalid Telegram update', headers=HEADERS) from exc
    try:
        started = perf_counter()
        result = await client.post(origin + path, content=bytes(body),
            headers={'Content-Type': 'application/json', 'x-vercel-protection-bypass': bypass,
                     'X-Telegram-Bot-Api-Secret-Token': secret})
        response_headers = {**HEADERS, 'Server-Timing': f'upstream;dur={(perf_counter()-started)*1000:.1f}'}
        if result.status_code == 204:
            return Response(status_code=204, headers=response_headers)
        if result.status_code == 200 and len(result.content) <= 65536:
            response = result.json()
            if isinstance(response, dict) and response.get('method') in ('sendMessage', 'editMessageText', 'sendRichMessage', 'sendDocument', 'sendPhoto', 'sendVideo', 'sendAudio', 'sendVoice', 'sendAnimation', 'sendVideoNote', 'sendSticker'):
                return Response(content=result.content, media_type='application/json', headers=response_headers)
    except (httpx.HTTPError, ValueError):
        pass
    # Never relay upstream HTML, exception details, redirect targets or credentials.
    raise HTTPException(status_code=503, detail='Factory is temporarily unavailable',
                        headers={**HEADERS, 'Retry-After': '5'})


# Only the dashboard's documented routes are reachable here. Authorization is
# validated by the application, not replaced by the private hosting bypass.
UUID_PATH = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
PUBLIC_API = {
    ('GET', '/api/v1/auth/methods'),
    ('POST', '/api/v1/auth/telegram/start'),
    ('POST', '/api/v1/auth/telegram/finish'),
    ('POST', '/api/v1/auth/telegram/cancel'),
}


def dashboard_api_allowed(method, path):
    if (method, path) in PUBLIC_API:
        return True
    patterns = {
        'GET': [r'/api/v1/me/preferences', r'/api/v1/tenants', r'/api/v1/templates',
            r'/api/v1/projects', rf'/api/v1/projects/{UUID_PATH}(?:/versions|/studio(?:/buttons|/submissions)?)?'],
        'PUT': [rf'/api/v1/projects/{UUID_PATH}/studio/form', r'/api/v1/me/preferences', rf'/api/v1/projects/{UUID_PATH}/studio/buttons/{UUID_PATH}'],
        'PATCH': [rf'/api/v1/projects/{UUID_PATH}(?:/studio)?'],
        'POST': [r'/api/v1/auth/logout', r'/api/v1/templates/(?:buttons|contact|form|welcome|auto-replies|command-menu)/projects',
            rf'/api/v1/projects/{UUID_PATH}/(?:stop|resume|studio/buttons/{UUID_PATH}/delete|studio/submissions/{UUID_PATH}/delete)'],
    }
    return any(re.fullmatch(pattern, path) for pattern in patterns.get(method, []))


@app.api_route('/dashboard', methods=['GET'])
@app.api_route('/dashboard/assets/{asset}', methods=['GET'])
async def dashboard_page(request: Request, client: Annotated[httpx.AsyncClient, Depends(upstream_client)],
    asset: str | None = None):
    if asset is not None and asset not in {'app.js','api.js','i18n.js','studio.js','forms.js','style.css'}:
        raise HTTPException(404, 'Not found', headers=HEADERS)
    return await forward_dashboard(request, client, request.url.path, page=True)


@app.api_route('/api/v1/{path:path}', methods=['GET','POST','PUT','PATCH','DELETE'])
async def dashboard_api(request: Request, client: Annotated[httpx.AsyncClient, Depends(upstream_client)]):
    path = request.url.path
    if not dashboard_api_allowed(request.method, path):
        raise HTTPException(404, 'Not found', headers=HEADERS)
    if (request.method, path) not in PUBLIC_API:
        authorization = request.headers.get('Authorization', '')
        if not authorization.startswith('Bearer ') or not 8 <= len(authorization) <= 8192:
            raise HTTPException(401, 'Sign in is required', headers=HEADERS)
    if request.method != 'GET':
        origin = request.headers.get('Origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'Cross-origin writes are not accepted', headers=HEADERS)
    return await forward_dashboard(request, client, path)


async def forward_dashboard(request, client, path, page=False):
    origin = os.environ.get('FACTORY_ORIGIN', '').rstrip('/')
    bypass = os.environ.get('FACTORY_PROTECTION_BYPASS', '')
    parsed = urlsplit(origin)
    if (len(bypass)<20 or parsed.scheme!='https' or not parsed.hostname
            or not parsed.hostname.endswith('.vercel.app') or parsed.username or parsed.password
            or parsed.port or parsed.path or parsed.query or parsed.fragment):
        raise HTTPException(503, 'Dashboard is unavailable', headers=HEADERS)
    if len(request.url.query)>4096:
        raise HTTPException(413, 'Query is too large', headers=HEADERS)
    # All credentials are headers; URL-borne access tokens and arbitrary destinations
    # are rejected rather than forwarded to an application or an access log.
    allowed_query = {'project'} if page else {'query','status','limit','offset','language_code','parent_id'}
    if any(key not in allowed_query for key in request.query_params):
        raise HTTPException(400, 'Unsupported query parameter', headers=HEADERS)
    body = bytearray()
    async for chunk in request.stream():
        if len(body)+len(chunk)>MAX_BODY:
            raise HTTPException(413, 'Payload is too large', headers=HEADERS)
        body.extend(chunk)
    headers = {'x-vercel-protection-bypass':bypass, 'Accept':'*/*' if page else 'application/json'}
    for name in ('Authorization','X-QMRSmith-Tenant-ID','Content-Type'):
        if value := request.headers.get(name):
            headers[name] = value
    if body and not headers.get('Content-Type','').startswith('application/json'):
        raise HTTPException(415, 'JSON is required', headers=HEADERS)
    try:
        result = await client.request(request.method, origin+path,
            params=request.query_params.multi_items(), content=bytes(body), headers=headers)
        if len(result.content)>MAX_BODY or result.is_redirect or result.status_code>=500:
            raise ValueError()
        content_type = result.headers.get('Content-Type','').split(';')[0]
        accepted = {'text/html','text/css','application/javascript','text/javascript'} if page else {'application/json'}
        if result.status_code != 204 and content_type not in accepted:
            raise ValueError()
        # Do not forward Set-Cookie, Location, hosting headers or exception pages.
        output = {**HEADERS, 'X-Content-Type-Options':'nosniff', 'Referrer-Policy':'no-referrer'}
        for name in ('Content-Security-Policy','X-Request-ID'):
            if value := result.headers.get(name):
                output[name] = value
        return Response(content=result.content, status_code=result.status_code,
            media_type=content_type or None, headers=output)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, 'Dashboard is temporarily unavailable', headers=HEADERS) from None
