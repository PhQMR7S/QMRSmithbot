"""Run after installing only `pip install .`, with no development extras."""
import asyncio

import httpx

from qmrsmithbot.api.app import app


async def main():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
        assert (await client.get('/health')).status_code == 200
        assert (await client.get('/dashboard')).status_code == 200
        assert (await client.get('/docs')).status_code == 200
        assert (await client.get('/dashboard/assets/app.js')).status_code == 200
        assert (await client.get('/api/v1/projects')).status_code == 401
    print('Runtime-only application import, dashboard assets, health and authentication checks passed.')


if __name__ == '__main__':
    asyncio.run(main())
