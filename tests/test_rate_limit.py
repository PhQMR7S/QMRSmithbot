import pytest
from fastapi import HTTPException, Request

from qmrsmithbot.config import settings
from qmrsmithbot.rate_limit import (
    RateLimitBackendUnavailable,
    RateLimitDecision,
    enforce_auth_rate_limit,
    rate_limiter,
)


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/dev/session",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
    )


@pytest.mark.asyncio
async def test_auth_rate_limit_allows_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    await enforce_auth_rate_limit(make_request())


@pytest.mark.asyncio
async def test_auth_rate_limit_rejects_excess(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_requests", 10)

    async def check(**_: object) -> RateLimitDecision:
        return RateLimitDecision(allowed=False, count=11)

    monkeypatch.setattr(rate_limiter, "check", check)
    with pytest.raises(HTTPException) as exc_info:
        await enforce_auth_rate_limit(make_request())
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_auth_rate_limit_fails_closed_when_backend_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    async def check(**_: object) -> RateLimitDecision:
        raise RateLimitBackendUnavailable("redis unavailable")

    monkeypatch.setattr(rate_limiter, "check", check)
    with pytest.raises(HTTPException) as exc_info:
        await enforce_auth_rate_limit(make_request())
    assert exc_info.value.status_code == 503
