import httpx
import pytest

from qmrsmithbot.api.app import app


@pytest.mark.asyncio
async def test_health_endpoint_includes_request_id() -> None:
    transport = httpx.ASGITransport(app=app)
    request_id = "9d9b9b9e-2d9d-4f43-8d0d-3d8a4f6a2d17"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "QMRSmithbot"}
    assert response.headers["X-Request-ID"] == request_id
