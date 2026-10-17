from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.api.dependencies import get_current_principal
from qmrsmithbot.auth.models import Principal
from qmrsmithbot.db.models import User
from qmrsmithbot.db.session import get_session
from qmrsmithbot.localization import LANGUAGES, MESSAGES, LanguageCode, resolve_language

router = APIRouter(prefix='/api/v1', tags=['preferences'])


class LanguagePreference(BaseModel):
    model_config = ConfigDict(extra='forbid')
    language_code: LanguageCode


class LanguageResponse(LanguagePreference):
    direction: Literal['rtl', 'ltr']


@router.get('/languages')
async def languages() -> list[dict[str, str]]:
    return list(LANGUAGES.values())


@router.get('/languages/{language_code}/messages')
async def messages(language_code: LanguageCode) -> dict[str, str]:
    return MESSAGES[language_code]


async def current_user(session: AsyncSession, principal: Principal) -> User:
    user = await session.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail='Account no longer exists')
    return user


@router.get('/me/preferences', response_model=LanguageResponse)
async def get_preferences(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LanguageResponse:
    user = await current_user(session, principal)
    code = resolve_language(user.language_code)
    return LanguageResponse(language_code=code, direction=LANGUAGES[code]['direction'])


@router.put('/me/preferences', response_model=LanguageResponse)
async def update_preferences(
    payload: LanguagePreference,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LanguageResponse:
    user = await current_user(session, principal)
    user.language_code = payload.language_code
    await session.flush()
    return LanguageResponse(
        language_code=payload.language_code,
        direction=LANGUAGES[payload.language_code]['direction'],
    )
