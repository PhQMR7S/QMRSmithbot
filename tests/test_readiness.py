import httpx
import pytest
from sqlalchemy.exc import OperationalError

from qmrsmithbot.api.app import app
from qmrsmithbot.api.readiness import readiness_session


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [None, OperationalError('secret-host', {}, Exception('password')),
                                   TimeoutError(), OSError('private-host')])
async def test_readiness_checks_database_and_hides_failure_details(failure):
    class Session:
        async def execute(self, _):
            if failure is not None:
                raise failure
            return self

        def scalar_one_or_none(self):
            return '20261017_03'

    async def session():
        yield Session()

    app.dependency_overrides[readiness_session] = session
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as client:
            response = await client.get('/ready')
        assert response.status_code == (200 if failure is None else 503)
        assert response.json() == {'status': 'ready' if failure is None else 'unavailable'}
        assert response.headers['cache-control'] == 'no-store'
        assert 'secret-host' not in response.text
        assert 'password' not in response.text
    finally:
        app.dependency_overrides.pop(readiness_session, None)
