from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import UUID

from aiogram.types import Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.db.models import BotProjectRecord, WorkflowVersionRecord
from qmrsmithbot.telegram.execution import (
    NonRetryableTelegramUpdateError,
    TelegramRuntimeContext,
    TelegramUpdateHandler,
)
from qmrsmithbot.telegram.queue import ClaimedTelegramUpdate
from qmrsmithbot.workflows.schema import WorkflowDefinition, WorkflowNode

EventKind = Literal["command", "message", "callback", "unknown"]


@dataclass(frozen=True, slots=True)
class TelegramEvent:
    kind: EventKind
    update_id: int
    chat_id: int | None
    user_id: int | None
    text: str | None
    command: str | None
    callback_data: str | None


@dataclass(frozen=True, slots=True)
class PublishedWorkflow:
    project_id: UUID
    tenant_id: UUID
    telegram_bot_id: int
    telegram_username: str | None
    version_id: UUID
    version: int
    definition: WorkflowDefinition


@dataclass(frozen=True, slots=True)
class TriggerMatch:
    node_id: str
    node_type: str


@dataclass(frozen=True, slots=True)
class DispatchPlan:
    project_id: UUID
    tenant_id: UUID
    update_id: int
    workflow_version_id: UUID
    workflow_version: int
    event: TelegramEvent
    triggers: tuple[TriggerMatch, ...]
    definition: WorkflowDefinition


class PublishedWorkflowRepository(Protocol):
    async def get_for_update(
        self, *, project_id: UUID, telegram_bot_id: int
    ) -> PublishedWorkflow | None: ...


class SQLAlchemyPublishedWorkflowRepository:
    """Read-only selection of the currently published workflow for a bot."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_update(
        self, *, project_id: UUID, telegram_bot_id: int
    ) -> PublishedWorkflow | None:
        row = await self.session.execute(
            select(BotProjectRecord, WorkflowVersionRecord)
            .join(
                WorkflowVersionRecord,
                (WorkflowVersionRecord.project_id == BotProjectRecord.id)
                & (WorkflowVersionRecord.version == BotProjectRecord.active_version),
            )
            .where(
                BotProjectRecord.id == project_id,
                BotProjectRecord.telegram_bot_id == telegram_bot_id,
                BotProjectRecord.status == "running",
                WorkflowVersionRecord.published_at.is_not(None),
            )
            .limit(1)
        )
        result = row.first()
        if result is None:
            return None
        project, version = result
        if project.tenant_id is None or project.telegram_bot_id is None:
            return None
        try:
            definition = WorkflowDefinition.model_validate(version.definition)
        except ValueError as exc:
            raise NonRetryableTelegramUpdateError(
                "published workflow definition is invalid"
            ) from exc
        return PublishedWorkflow(
            project_id=project.id,
            tenant_id=project.tenant_id,
            telegram_bot_id=project.telegram_bot_id,
            telegram_username=project.telegram_username,
            version_id=version.id,
            version=version.version,
            definition=definition,
        )


class TelegramEventClassifier:
    """Deterministically classifies an aiogram Update without executing workflow logic."""

    _COMMAND_RE = re.compile(
        r"^/([A-Za-z0-9_]{1,64})(?:@([A-Za-z0-9_]{1,255}))?(?:\s|$)"
    )

    @classmethod
    def classify(cls, update: Update, *, telegram_username: str | None = None) -> TelegramEvent:
        message = update.message or update.edited_message
        if message is not None:
            text = message.text
            command = cls._extract_command(text, telegram_username=telegram_username)
            if command is not None:
                return TelegramEvent(
                    kind="command",
                    update_id=update.update_id,
                    chat_id=message.chat.id,
                    user_id=message.from_user.id if message.from_user else None,
                    text=text,
                    command=command,
                    callback_data=None,
                )
            if text is not None:
                return TelegramEvent(
                    kind="message",
                    update_id=update.update_id,
                    chat_id=message.chat.id,
                    user_id=message.from_user.id if message.from_user else None,
                    text=text,
                    command=None,
                    callback_data=None,
                )

        callback = update.callback_query
        if callback is not None:
            return TelegramEvent(
                kind="callback",
                update_id=update.update_id,
                chat_id=callback.message.chat.id if callback.message else None,
                user_id=callback.from_user.id if callback.from_user else None,
                text=None,
                command=None,
                callback_data=callback.data,
            )

        return TelegramEvent(
            kind="unknown",
            update_id=update.update_id,
            chat_id=None,
            user_id=None,
            text=None,
            command=None,
            callback_data=None,
        )

    @classmethod
    def _extract_command(cls, text: str | None, *, telegram_username: str | None) -> str | None:
        if not text:
            return None
        match = cls._COMMAND_RE.match(text)
        if match is None:
            return None
        target = match.group(2)
        username = telegram_username.casefold().lstrip("@").strip() if telegram_username else None
        if target and (username is None or target.casefold() != username):
            return None
        return match.group(1).casefold()


class TelegramTriggerResolver:
    """Resolves only explicitly supported, bounded trigger matching rules."""

    @staticmethod
    def resolve(definition: WorkflowDefinition, event: TelegramEvent) -> tuple[TriggerMatch, ...]:
        return tuple(
            TriggerMatch(node_id=node.id, node_type=node.type)
            for node in definition.nodes
            if node.type.startswith("trigger.") and TelegramTriggerResolver._matches(node, event)
        )

    @staticmethod
    def _matches(node: WorkflowNode, event: TelegramEvent) -> bool:
        config: dict[str, Any] = node.config
        expected_kind = node.type.removeprefix("trigger.")
        if event.kind != expected_kind:
            return False
        if event.kind == "command":
            values = config.get("commands", config.get("command"))
            if values is None:
                return True
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                return False
            expected = {value.strip().lstrip("/").casefold() for value in values if value.strip()}
            return event.command in expected
        if event.kind == "message":
            return TelegramTriggerResolver._match_text(event.text, config)
        if event.kind == "callback":
            return TelegramTriggerResolver._match_callback(event.callback_data, config)
        return False

    @staticmethod
    def _match_text(text: str | None, config: dict[str, Any]) -> bool:
        if text is None:
            return False
        if "text" in config:
            return isinstance(config["text"], str) and text == config["text"]
        if "starts_with" in config:
            return isinstance(config["starts_with"], str) and text.startswith(config["starts_with"])
        if "contains" in config:
            return isinstance(config["contains"], str) and config["contains"] in text
        return True

    @staticmethod
    def _match_callback(data: str | None, config: dict[str, Any]) -> bool:
        if data is None:
            return False
        if "data" in config:
            return isinstance(config["data"], str) and data == config["data"]
        if "starts_with" in config:
            return isinstance(config["starts_with"], str) and data.startswith(config["starts_with"])
        return True


class TelegramWorkflowDispatcher:
    """Builds an immutable dispatch plan from one durable Telegram inbox item."""

    def __init__(self, repository: PublishedWorkflowRepository) -> None:
        self.repository = repository

    async def dispatch(self, item: ClaimedTelegramUpdate) -> DispatchPlan | None:
        update = self._validate_update(item.payload)
        return await self.dispatch_update(
            project_id=item.project_id,
            telegram_bot_id=item.telegram_bot_id,
            update=update,
            update_id=item.update_id,
        )

    async def dispatch_update(
        self,
        *,
        project_id: UUID,
        telegram_bot_id: int,
        update: Update,
        update_id: int,
    ) -> DispatchPlan | None:
        workflow = await self.repository.get_for_update(
            project_id=project_id,
            telegram_bot_id=telegram_bot_id,
        )
        if workflow is None:
            return None
        event = TelegramEventClassifier.classify(
            update, telegram_username=workflow.telegram_username
        )
        triggers = TelegramTriggerResolver.resolve(workflow.definition, event)
        if not triggers:
            return None
        return DispatchPlan(
            project_id=workflow.project_id,
            tenant_id=workflow.tenant_id,
            update_id=update_id,
            workflow_version_id=workflow.version_id,
            workflow_version=workflow.version,
            event=event,
            triggers=triggers,
            definition=workflow.definition,
        )

    @staticmethod
    def _validate_update(payload: dict) -> Update:
        try:
            return Update.model_validate(payload)
        except ValueError as exc:
            raise NonRetryableTelegramUpdateError("persisted Telegram update is invalid") from exc


class DispatchPlanSink(Protocol):
    async def accept(self, *, plan: DispatchPlan, context: TelegramRuntimeContext) -> None: ...


class TelegramWorkflowDispatchHandler(TelegramUpdateHandler):
    """Worker adapter; the sink is the intentionally separate future workflow runtime."""

    def __init__(self, dispatcher: TelegramWorkflowDispatcher, sink: DispatchPlanSink) -> None:
        self.dispatcher = dispatcher
        self.sink = sink

    async def handle(self, *, update: Update, context: TelegramRuntimeContext) -> None:
        plan = await self.dispatcher.dispatch_update(
            project_id=context.project_id,
            telegram_bot_id=context.telegram_bot_id,
            update=update,
            update_id=context.update_id,
        )
        if plan is not None:
            await self.sink.accept(plan=plan, context=context)
