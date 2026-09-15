from __future__ import annotations

from unittest.mock import MagicMock

from qmrsmithbot.workflows.action_registry import build_action_registry
from qmrsmithbot.workflows.actions import ActionRegistry


def test_build_action_registry_registers_builtin_external_actions():
    registry = build_action_registry(MagicMock())
    assert isinstance(registry, ActionRegistry)
    for action_type in (
        "action.message",
        "action.edit_message",
        "action.delete_message",
        "action.http",
    ):
        handler = registry.resolve(action_type)
        assert handler.action_type == action_type
