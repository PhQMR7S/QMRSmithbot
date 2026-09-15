from uuid import uuid4

import pytest
from aiogram.types import Update

from qmrsmithbot.telegram.dispatcher import (
    DispatchPlan,
    PublishedWorkflow,
    TelegramEventClassifier,
    TelegramTriggerResolver,
    TelegramWorkflowDispatcher,
)
from qmrsmithbot.workflows.schema import WorkflowDefinition


def _update(payload: dict) -> Update:
    return Update.model_validate(payload)


def _definition(*nodes: dict) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate({"nodes": list(nodes)})


class FakeRepository:
    def __init__(self, workflow: PublishedWorkflow | None) -> None:
        self.workflow = workflow
        self.calls: list[tuple] = []

    async def get_for_update(self, *, project_id, telegram_bot_id):
        self.calls.append((project_id, telegram_bot_id))
        return self.workflow


def _workflow(definition: WorkflowDefinition, *, username: str = "my_bot") -> PublishedWorkflow:
    return PublishedWorkflow(
        project_id=uuid4(),
        tenant_id=uuid4(),
        telegram_bot_id=123,
        telegram_username=username,
        version_id=uuid4(),
        version=7,
        definition=definition,
    )


def test_command_classifier_normalizes_command_and_accepts_bot_mention() -> None:
    event = TelegramEventClassifier.classify(
        _update(
            {
                "update_id": 1,
                "message": {
                    "message_id": 2,
                    "date": 1,
                    "chat": {"id": 10, "type": "private"},
                    "text": "/Start@My_Bot hello",
                },
            }
        ),
        telegram_username="my_bot",
    )

    assert event.kind == "command"
    assert event.command == "start"
    assert event.chat_id == 10


def test_command_for_another_bot_is_not_classified_as_command() -> None:
    event = TelegramEventClassifier.classify(
        _update(
            {
                "update_id": 1,
                "message": {
                    "message_id": 2,
                    "date": 1,
                    "chat": {"id": 10, "type": "private"},
                    "text": "/start@another_bot",
                },
            }
        ),
        telegram_username="my_bot",
    )

    assert event.kind == "message"
    assert event.command is None


def test_trigger_resolver_supports_bounded_matching_rules() -> None:
    definition = _definition(
        {"id": "start", "type": "trigger.command", "config": {"command": "/start"}},
        {"id": "help", "type": "trigger.command", "config": {"commands": ["help", "info"]}},
        {"id": "contains", "type": "trigger.message", "config": {"contains": "hello"}},
    )
    event = TelegramEventClassifier.classify(
        _update(
            {
                "update_id": 1,
                "message": {
                    "message_id": 2,
                    "date": 1,
                    "chat": {"id": 10, "type": "private"},
                    "text": "/start",
                },
            }
        ),
        telegram_username="my_bot",
    )

    matches = TelegramTriggerResolver.resolve(definition, event)
    assert len(matches) == 1
    assert matches[0].node_id == "start"


@pytest.mark.asyncio
async def test_dispatch_selects_published_workflow_and_returns_plan() -> None:
    project_id = uuid4()
    definition = _definition(
        {"id": "start", "type": "trigger.command", "config": {"command": "start"}}
    )
    workflow = _workflow(definition)
    workflow = PublishedWorkflow(
        project_id=project_id,
        tenant_id=workflow.tenant_id,
        telegram_bot_id=workflow.telegram_bot_id,
        telegram_username=workflow.telegram_username,
        version_id=workflow.version_id,
        version=workflow.version,
        definition=workflow.definition,
    )
    repository = FakeRepository(workflow)

    plan = await TelegramWorkflowDispatcher(repository).dispatch_update(
        project_id=project_id,
        telegram_bot_id=123,
        update=_update(
            {
                "update_id": 9,
                "message": {
                    "message_id": 2,
                    "date": 1,
                    "chat": {"id": 10, "type": "private"},
                    "text": "/start",
                },
            }
        ),
        update_id=9,
    )

    assert isinstance(plan, DispatchPlan)
    assert plan.project_id == project_id
    assert plan.workflow_version == 7
    assert [match.node_id for match in plan.triggers] == ["start"]
    assert repository.calls == [(project_id, 123)]


@pytest.mark.asyncio
async def test_dispatch_returns_none_when_no_trigger_matches() -> None:
    definition = _definition(
        {"id": "help", "type": "trigger.command", "config": {"command": "help"}}
    )
    workflow = _workflow(definition)
    repository = FakeRepository(workflow)

    plan = await TelegramWorkflowDispatcher(repository).dispatch_update(
        project_id=workflow.project_id,
        telegram_bot_id=workflow.telegram_bot_id,
        update=_update(
            {
                "update_id": 9,
                "message": {
                    "message_id": 2,
                    "date": 1,
                    "chat": {"id": 10, "type": "private"},
                    "text": "/start",
                },
            }
        ),
        update_id=9,
    )

    assert plan is None
