from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.auth.telegram_login import TelegramLoginError, TelegramLoginService
from qmrsmithbot.config import settings
from qmrsmithbot.db.session import get_session
from qmrsmithbot.rate_limit import enforce_auth_rate_limit

router = APIRouter(prefix='/api/v1/auth', tags=['authentication'])
HEADERS = {'Cache-Control': 'no-store', 'Pragma': 'no-cache', 'Referrer-Policy': 'no-referrer'}


class TelegramLoginFinishRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    challenge_id: str = Field(pattern=r'^[A-Za-z0-9_-]{32}$')
    browser_secret: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')


@router.get('/methods')
async def authentication_methods():
    return JSONResponse(content={'oidc': settings.auth_oidc_enabled,
                                 'telegram': settings.auth_telegram_enabled}, headers=HEADERS)


@router.post('/telegram/start', dependencies=[Depends(enforce_auth_rate_limit)])
async def start_telegram_login(session: Annotated[AsyncSession, Depends(get_session)]):
    if not settings.auth_telegram_enabled:
        raise HTTPException(status_code=404, detail='Telegram login is unavailable', headers=HEADERS)
    try:
        result = await TelegramLoginService(session).begin()
    except TelegramLoginError as exc:
        raise HTTPException(status_code=503, detail='Telegram login is unavailable', headers=HEADERS) from exc
    return JSONResponse(content=jsonable_encoder(result), headers=HEADERS)


@router.post('/telegram/finish', dependencies=[Depends(enforce_auth_rate_limit)])
async def finish_telegram_login(payload: TelegramLoginFinishRequest, request: Request,
        session: Annotated[AsyncSession, Depends(get_session)]):
    if not settings.auth_telegram_enabled:
        raise HTTPException(status_code=404, detail='Telegram login is unavailable', headers=HEADERS)
    try:
        result = await TelegramLoginService(session).finish(payload.challenge_id, payload.browser_secret,
            user_agent=request.headers.get('User-Agent'),
            ip_address=request.client.host if request.client else None)
    except TelegramLoginError as exc:
        raise HTTPException(status_code=401, detail='Invalid or expired login request', headers=HEADERS) from exc
    if result is None:
        return JSONResponse(status_code=202, content={'status': 'pending'}, headers=HEADERS)
    return JSONResponse(content=jsonable_encoder(result), headers=HEADERS)


@router.get('/telegram/start', include_in_schema=False)
async def reject_get_start():
    return Response(status_code=405, headers={**HEADERS, 'Allow': 'POST'})


@router.post('/telegram/cancel', dependencies=[Depends(enforce_auth_rate_limit)])
async def cancel_telegram_login(payload: TelegramLoginFinishRequest,
        session: Annotated[AsyncSession, Depends(get_session)]):
    if not settings.auth_telegram_enabled:
        raise HTTPException(status_code=404, detail='Telegram login is unavailable', headers=HEADERS)
    try:
        await TelegramLoginService(session).cancel(payload.challenge_id, payload.browser_secret)
    except TelegramLoginError as exc:
        raise HTTPException(status_code=401, detail='Invalid or expired login request', headers=HEADERS) from exc
    return Response(status_code=204, headers=HEADERS)
