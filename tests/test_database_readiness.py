"""Database-backed readiness must not claim success without a working database."""

import importlib

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from qmrsmithbot.api.app import app


class FakeResult:
    def scalar_one_or_none(self):
        return "20261017_01"


class FakeSession:
    def __init__(self, fail=False):
        self.fail = fail

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, _statement):
        if self.fail:
            raise OperationalError("SELECT 1", {}, Exception("private connection string"))
        return FakeResult()


@pytest.mark.asyncio
@pytest.mark.parametrize(("fail", "expected"), [(False, 200), (True, 503)])
async def test_readiness_verifies_database_and_does_not_expose_errors(
    monkeypatch, fail, expected
):
    module = importlib.import_module("qmrsmithbot.api.app")

    monkeypatch.setattr(module, "SessionFactory", lambda: FakeSession(fail))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        response = await client.get("/ready")
    assert response.status_code == expected
    assert "private connection string" not in response.text
