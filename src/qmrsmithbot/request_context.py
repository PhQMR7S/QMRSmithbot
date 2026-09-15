from __future__ import annotations

from contextvars import ContextVar, Token
from uuid import UUID, uuid4

from fastapi import Request

_request_id: ContextVar[str | None] = ContextVar("qmrsmithbot_request_id", default=None)


def resolve_request_id(value: str | None) -> str:
    if value:
        try:
            return str(UUID(value.strip()))
        except (AttributeError, ValueError):
            pass
    return str(uuid4())


def set_request_id(request_id: str) -> Token[str | None]:
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def get_request_id() -> str | None:
    return _request_id.get()


def attach_request_id(request: Request) -> str:
    request_id = resolve_request_id(request.headers.get("X-Request-ID"))
    request.state.request_id = request_id
    return request_id
