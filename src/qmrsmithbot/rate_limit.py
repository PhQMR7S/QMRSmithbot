from __future__ import annotations

from dataclasses import dataclass
from secrets import token_urlsafe

import redis.asyncio as redis
from redis.exceptions import RedisError
from fastapi import HTTPException, Request, status

from qmrsmithbot.config import settings

_SLIDING_WINDOW_SCRIPT = """
local now_parts = redis.call('TIME')
local now = tonumber(now_parts[1]) * 1000000 + tonumber(now_parts[2])
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local cutoff = now - window
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, cutoff)
local count = redis.call('ZCARD', KEYS[1])
if count >= limit then
    return {0, count}
end
local member = ARGV[3] .. ':' .. tostring(now)
redis.call('ZADD', KEYS[1], now, member)
redis.call('EXPIRE', KEYS[1], math.ceil(window / 1000000))
return {1, count + 1}
"""


class RateLimitBackendUnavailable(RuntimeError):
    """Raised when the configured rate-limit backend cannot be reached."""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    count: int


class RedisRateLimiter:
    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    async def check(self, *, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        try:
            result = await self.client.eval(
                _SLIDING_WINDOW_SCRIPT,
                1,
                key,
                window_seconds * 1_000_000,
                limit,
                token_urlsafe(12),
            )
        except RedisError as exc:
            raise RateLimitBackendUnavailable("rate-limit backend unavailable") from exc
        allowed, count = int(result[0]), int(result[1])
        return RateLimitDecision(allowed=bool(allowed), count=count)

    async def close(self) -> None:
        await self.client.aclose()


rate_limiter = RedisRateLimiter(redis.from_url(settings.redis_url))


async def enforce_auth_rate_limit(request: Request) -> None:
    if not settings.rate_limit_enabled:
        return
    source = request.client.host if request.client is not None else "unknown"
    key = f"qmrsmithbot:ratelimit:auth:ip:{source}"
    try:
        decision = await rate_limiter.check(
            key=key,
            limit=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )
    except RateLimitBackendUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="security control unavailable",
        ) from exc
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many authentication requests",
        )


async def close_rate_limiter() -> None:
    await rate_limiter.close()
