import pytest
from aiogram.types import Update

from qmrsmithbot.telegram.dispatcher import TelegramEventClassifier, TelegramTriggerResolver
from qmrsmithbot.templates.catalog import TemplateOptions, get_template


@pytest.mark.parametrize('template,trigger,text', [
    ('welcome', None, '/start'),
    ('auto-replies', 'سعر', 'سعر'),
    ('command-menu', 'help', '/help'),
])
def test_generated_workflows_match_real_dispatcher(template, trigger, text):
    options = TemplateOptions(rules=[] if trigger is None else [{'trigger': trigger, 'response': 'Answer'}])
    definition = get_template(template).build(options)
    update = Update.model_validate({'update_id': 1, 'message': {
        'message_id': 1, 'date': 0, 'chat': {'id': 7, 'type': 'private'},
        'from': {'id': 7, 'is_bot': False, 'first_name': 'Test'}, 'text': text}})
    event = TelegramEventClassifier.classify(update)
    assert len(TelegramTriggerResolver.resolve(definition, event)) == 1


def test_builds_are_independent():
    t = get_template('welcome')
    first = t.build(TemplateOptions(welcome='A'))
    second = t.build(TemplateOptions(welcome='B'))
    assert first.nodes[1].config['text'] == 'A'
    assert second.nodes[1].config['text'] == 'B'


@pytest.mark.parametrize('rules', [
    [{'trigger': ' ', 'response': 'A'}],
    [{'trigger': 'x', 'response': 'A'}, {'trigger': 'x', 'response': 'B'}],
])
def test_invalid_rules(rules):
    with pytest.raises(ValueError):
        TemplateOptions(rules=rules)
