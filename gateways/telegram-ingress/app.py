"""Public Telegram-only ingress. Private Vercel credentials stay on the server."""
import hashlib
import hmac
import json
import os
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
MAX_BODY = 1_048_576
HEADERS = {'Cache-Control': 'no-store'}


async def upstream_client():
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
        result = await client.post(origin + path, content=bytes(body),
            headers={'Content-Type': 'application/json', 'x-vercel-protection-bypass': bypass,
                     'X-Telegram-Bot-Api-Secret-Token': secret})
        if result.status_code == 204:
            return Response(status_code=204, headers=HEADERS)
        if result.status_code == 200 and len(result.content) <= 65536:
            response = result.json()
            if isinstance(response, dict) and response.get('method') in ('sendMessage', 'editMessageText', 'sendRichMessage'):
                return Response(content=result.content, media_type='application/json', headers=HEADERS)
    except (httpx.HTTPError, ValueError):
        pass
    # Never relay upstream HTML, exception details, redirect targets or credentials.
    raise HTTPException(status_code=503, detail='Factory is temporarily unavailable',
                        headers={**HEADERS, 'Retry-After': '5'})
