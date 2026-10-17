from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import SecretStr

from qmrsmithbot.config import settings
from qmrsmithbot.telegram.inline_runtime import (
    InlineBotError,
    child_webhook_secret,
    compile_text_program,
)
from qmrsmithbot.templates.catalog import CATALOG, TemplateOptions


@pytest.mark.parametrize('template', CATALOG)
def test_text_runtime_accepts_all_factory_templates(template):
    rules = [] if template.mode == 'welcome' else [{'trigger': 'help', 'response': 'Details'}]
    definition = template.build(TemplateOptions(welcome='Hello', rules=rules)).model_dump(mode='json')
    program = compile_text_program(definition)
    assert program.commands['start'] == 'Hello'
    if template.mode == 'message':
        assert program.messages == {'help': 'Details'}
    if template.mode == 'command':
        assert program.commands['help'] == 'Details'


@pytest.mark.parametrize('mutation', ['http', 'variables', 'chain', 'unconnected', 'config', 'duplicate'])
def test_text_runtime_rejects_unsupported_execution(mutation):
    definition = CATALOG[0].build(TemplateOptions()).model_dump(mode='json')
    if mutation == 'http':
        definition['nodes'][1]['type'] = 'action.http'
    elif mutation == 'variables':
        definition['variables'] = {'name': 'value'}
    elif mutation == 'chain':
        definition['edges'].append({'source': 'welcome', 'target': 'start'})
    elif mutation == 'unconnected':
        definition['nodes'].append({'id': 'unused', 'type': 'action.message', 'config': {'text': 'No'}})
    elif mutation == 'config':
        definition['nodes'][1]['config']['parse_mode'] = 'HTML'
    else:
        node = deepcopy(definition['nodes'][0])
        node['id'] = 'another'
        definition['nodes'].append(node)
        definition['edges'].append({'source': 'another', 'target': 'welcome'})
    with pytest.raises(ValueError):
        compile_text_program(definition)


def test_child_secret_is_stable_and_unique_per_project(monkeypatch):
    monkeypatch.setattr(settings, 'telegram_factory_webhook_secret', SecretStr('S'*40))
    project = uuid4()
    assert child_webhook_secret(project) == child_webhook_secret(str(project))
    assert child_webhook_secret(project) != child_webhook_secret(uuid4())
    assert len(child_webhook_secret(project)) == 64
    monkeypatch.setattr(settings, 'telegram_factory_webhook_secret', SecretStr(''))
    with pytest.raises(InlineBotError):
        child_webhook_secret(project)
