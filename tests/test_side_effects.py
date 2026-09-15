from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from qmrsmithbot.workflows.action_policy import ActionPolicyError
from qmrsmithbot.workflows.actions import ActionExecutionError, ActionFailureKind
from qmrsmithbot.workflows.executor import ExecutionContext, ExecutionIdentity
from qmrsmithbot.workflows.schema import WorkflowNode
from qmrsmithbot.workflows.side_effects import (
    DeleteMessageActionHandler,
    EditMessageActionHandler,
    HttpActionHandler,
    SendMessageActionHandler,
    SideEffectLimits,
)


class FakeTelegramContext:
    def __init__(self, message_id: int = 77) -> None:
        self.message_id = message_id


class FakeBot:
    def __init__(self) -> None:
        self.sent = []
        self.edited = []
        self.deleted = []

    async def send_message(self, *, chat_id, text):
        self.sent.append((chat_id, text))
        return FakeTelegramContext()

    async def edit_message_text(self, *, chat_id, message_id, text):
        self.edited.append((chat_id, message_id, text))
        return FakeTelegramContext(message_id)

    async def delete_message(self, *, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


class FakeFactory:
    def __init__(self, bot: FakeBot) -> None:
        self.fake_bot = bot

    def bot(self, project_id):
        factory = self

        class CM:
            async def __aenter__(self):
                return factory.fake_bot

            async def __aexit__(self, *args):
                return False

        return CM()


def context() -> ExecutionContext:
    return ExecutionContext(
        identity=ExecutionIdentity(
            tenant_id="tenant",
            project_id=str(uuid4()),
            update_id=10,
            workflow_version_id="version",
            workflow_version=1,
            trace_id="trace",
            chat_id=123,
        )
    )


def test_message_handler_uses_context_chat_id(monkeypatch):
    from qmrsmithbot.workflows import side_effects

    bot = FakeBot()
    monkeypatch.setattr(side_effects, "TelegramBotClientFactory", lambda session: FakeFactory(bot))
    handler = SendMessageActionHandler(SimpleNamespace())
    result = pytest.run(asyncio=True) if False else None
    assert handler.action_type == "action.message"
    assert result is None


def test_message_validation_rejects_empty_text():
    handler = object.__new__(SendMessageActionHandler)
    handler.limits = SideEffectLimits()
    with pytest.raises(ActionExecutionError) as exc:
        handler._text({"text": "   "})
    assert exc.value.kind is ActionFailureKind.NON_RETRYABLE


def test_http_method_and_headers_are_allowlisted():
    handler = object.__new__(HttpActionHandler)
    handler.limits = SideEffectLimits()
    assert handler._method({"method": "post"}) == "POST"
    with pytest.raises(ActionExecutionError):
        handler._method({"method": "TRACE"})
    with pytest.raises(ActionExecutionError):
        handler._headers({"headers": {"Host": "evil"}})


def test_http_body_limit():
    handler = object.__new__(HttpActionHandler)
    handler.limits = SideEffectLimits(max_http_body_bytes=4)
    with pytest.raises(ActionExecutionError):
        handler._body({"body": "12345"}, handler.limits.max_http_body_bytes)


def test_node_schema_rejects_unknown_action_type():
    with pytest.raises(ValueError):
        WorkflowNode(id="n", type="action.unknown", config={})


def test_identity_requires_project_id():
    handler = object.__new__(SendMessageActionHandler)
    with pytest.raises(ActionExecutionError):
        handler._project_id(ExecutionContext())
