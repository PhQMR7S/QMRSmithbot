from __future__ import annotations

from uuid import uuid4

import pytest

from qmrsmithbot.workflows.actions import ActionExecutionError, ActionFailureKind
from qmrsmithbot.workflows.executor import ExecutionContext, ExecutionIdentity
from qmrsmithbot.workflows.schema import WorkflowNode
from qmrsmithbot.workflows.side_effects import (
    HttpActionHandler,
    SendMessageActionHandler,
    SideEffectLimits,
)


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
