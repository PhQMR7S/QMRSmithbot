"""A small, explicitly bounded transport for the factory's plain-text templates."""
import hashlib
import hmac
import re
from dataclasses import dataclass

from sqlalchemy import select

from qmrsmithbot.config import settings
from qmrsmithbot.db.factory_models import TelegramInlineBotRecord, TelegramInlineUpdateRecord
from qmrsmithbot.db.models import BotProjectRecord, WorkflowVersionRecord
from qmrsmithbot.telegram.dispatcher import TelegramEventClassifier
from qmrsmithbot.workflows.schema import WorkflowDefinition


class InlineBotError(ValueError):
    pass


def child_webhook_secret(project_id):
    key = settings.telegram_factory_webhook_secret.get_secret_value()
    if len(key) < 32:
        raise InlineBotError('Inline runtime is unavailable')
    return hmac.new(key.encode(), ('child:' + str(project_id)).encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class TextProgram:
    commands: dict[str, str]
    messages: dict[str, str]


def compile_text_program(raw):
    definition = WorkflowDefinition.model_validate(raw)
    if definition.schema_version != 1 or definition.variables:
        raise InlineBotError('This workflow needs the advanced runtime')
    nodes = {node.id: node for node in definition.nodes}
    commands, messages, used = {}, {}, set()
    for node in definition.nodes:
        if node.type == 'action.message':
            if set(node.config) != {'text'} or not isinstance(node.config['text'], str) or not 0 < len(node.config['text']) <= 3000:
                raise InlineBotError('Only bounded plain-text messages are supported')
            continue
        key = 'command' if node.type == 'trigger.command' else 'text' if node.type == 'trigger.message' else None
        if key is None or set(node.config) != {key}:
            raise InlineBotError('This workflow needs the advanced runtime')
        trigger = node.config[key]
        if not isinstance(trigger, str) or not trigger.strip() or len(trigger) > 100:
            raise InlineBotError('Invalid text trigger')
        if key == 'command' and not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', trigger):
            raise InlineBotError('Invalid command')
        edges = [edge for edge in definition.edges if edge.source == node.id]
        if len(edges) != 1 or edges[0].condition is not None:
            raise InlineBotError('Each trigger must have exactly one plain-text reply')
        target = nodes[edges[0].target]
        if target.type != 'action.message' or any(e.source == target.id for e in definition.edges):
            raise InlineBotError('Chained actions require the advanced runtime')
        bucket = commands if key == 'command' else messages
        if trigger in bucket:
            raise InlineBotError('Duplicate trigger')
        bucket[trigger] = target.config.get('text')
        used.update((node.id, target.id))
    if used != set(nodes) or 'start' not in commands:
        raise InlineBotError('A start reply and connected nodes are required')
    return TextProgram(commands, messages)


async def process_inline_update(session, project_id, update):
    project = await session.scalar(select(BotProjectRecord).where(
        BotProjectRecord.id == project_id).with_for_update())
    state = await session.get(TelegramInlineBotRecord, project_id)
    if project is not None and project.status == 'stopped':
        return None
    if (project is None or state is None or not state.enabled or project.status != 'running'
            or project.telegram_bot_id is None or project.active_version is None):
        raise InlineBotError('Runtime activation is incomplete')
    cached = await session.get(TelegramInlineUpdateRecord, (project_id, update.update_id))
    if cached is not None:
        return cached.response
    version = await session.scalar(select(WorkflowVersionRecord).where(
        WorkflowVersionRecord.project_id == project_id,
        WorkflowVersionRecord.version == project.active_version,
        WorkflowVersionRecord.published_at.is_not(None)))
    if version is None:
        raise InlineBotError('Published workflow is unavailable')
    program = compile_text_program(version.definition)
    message = update.message
    response = None
    if message and message.chat.type == 'private' and message.from_user and not message.from_user.is_bot:
        event = TelegramEventClassifier.classify(update, telegram_username=project.telegram_username)
        text = program.commands.get(event.command) if event.kind == 'command' else program.messages.get(event.text)
        if text is not None:
            response = {'method': 'sendMessage', 'chat_id': message.chat.id, 'text': text}
    session.add(TelegramInlineUpdateRecord(project_id=project_id, update_id=update.update_id,
                                           response=response))
    await session.flush()
    return response
