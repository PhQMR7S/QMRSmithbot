import pytest
from sqlalchemy.exc import OperationalError

from qmrsmithbot.config import Settings
from qmrsmithbot.rate_limit import PostgresRateLimiter, RateLimitBackendUnavailable


def test_rate_limit_backend_is_explicit_and_validated():
    assert Settings(rate_limit_backend='postgresql').rate_limit_backend == 'postgresql'
    with pytest.raises(ValueError):
        Settings(rate_limit_backend='in-memory')


@pytest.mark.asyncio
async def test_postgres_limiter_fails_closed_without_leaking_connection_details():
    class BrokenSession:
        async def __aenter__(self):
            raise OperationalError('private-host', {}, Exception('private-password'))

        async def __aexit__(self, *args):
            return None

    limiter = PostgresRateLimiter(BrokenSession)
    with pytest.raises(RateLimitBackendUnavailable, match='^rate-limit backend unavailable$'):
        await limiter.check(key='private-ip', limit=3, window_seconds=60)


@pytest.mark.asyncio
@pytest.mark.parametrize('limit,window', [(0, 60), (1, 0), (-1, 1)])
async def test_postgres_limiter_rejects_invalid_windows(limit, window):
    with pytest.raises(ValueError):
        await PostgresRateLimiter().check(key='test', limit=limit, window_seconds=window)
