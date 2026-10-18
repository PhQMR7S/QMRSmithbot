"""Database-backed readiness must not claim success without a working database."""

import importlib

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from qmrsmithbot.api.app import app


class FakeResult:
    def __init__(self, revision):
        self.revision = revision

    def scalar_one_or_none(self):
        return self.revision


class FakeSession:
    def __init__(self, fail=False, revision="20261018_06"):
        self.fail = fail
        self.revision = revision

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, _statement):
        if self.fail:
            raise OperationalError("SELECT 1", {}, Exception("private connection string"))
        return FakeResult(self.revision)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fail", "revision", "expected"),
    [
        (False, "20261018_06", 200),
        (False, "0007", 503),
        (False, None, 503),
        (True, "20261018_06", 503),
    ],
)
async def test_readiness_verifies_database_and_does_not_expose_errors(
    monkeypatch, fail, revision, expected
):
    module = importlib.import_module("qmrsmithbot.api.readiness")

    monkeypatch.setattr(module, "SessionFactory", lambda: FakeSession(fail, revision))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        response = await client.get("/ready")
    assert response.status_code == expected
    assert "private connection string" not in response.text
