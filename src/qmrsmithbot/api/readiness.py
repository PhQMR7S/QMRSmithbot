import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.config import settings
from qmrsmithbot.db.session import SessionFactory

router = APIRouter(tags=['operations'])


async def readiness_session():
    # This probe is read-only; rollback/connection cleanup happens on context exit.
    async with SessionFactory() as session:
        yield session


@router.get('/ready', include_in_schema=False)
async def readiness(session: Annotated[AsyncSession, Depends(readiness_session)]):
    try:
        async with asyncio.timeout(5):
            # Check the application schema and permissions, not just TCP connectivity.
            await session.execute(text('SELECT id, language_code FROM users LIMIT 0'))
            await session.execute(text('SELECT bot_id, update_id FROM factory_updates LIMIT 0'))
            if settings.rate_limit_enabled and settings.rate_limit_backend == 'postgresql':
                await session.execute(text(
                    'SELECT key, count, expires_at FROM security_rate_limits LIMIT 0'))
            applied = await session.execute(text('SELECT version_num FROM alembic_version'))
            if applied.scalar_one_or_none() != '20261017_02':
                return JSONResponse(status_code=503, content={'status': 'unavailable'},
                                    headers={'Cache-Control': 'no-store', 'Retry-After': '5'})
    except (SQLAlchemyError, OSError, TimeoutError):
        return JSONResponse(status_code=503, content={'status': 'unavailable'},
                            headers={'Cache-Control': 'no-store', 'Retry-After': '5'})
    return JSONResponse(content={'status': 'ready'}, headers={'Cache-Control': 'no-store'})
