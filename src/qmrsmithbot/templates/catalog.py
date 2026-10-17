from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from qmrsmithbot.localization import LanguageCode
from qmrsmithbot.workflows.schema import WorkflowDefinition


class ReplyRule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    trigger: str = Field(min_length=1, max_length=100)
    response: str = Field(min_length=1, max_length=3000)


class TemplateOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    language_code: LanguageCode = 'ar'
    welcome: str | None = Field(default=None, min_length=1, max_length=3000)
    rules: list[ReplyRule] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def validate_rules(self):
        triggers = [r.trigger for r in self.rules]
        if any(not value.strip() for value in triggers):
            raise ValueError('Reply triggers must not be blank')
        if len(triggers) != len(set(triggers)):
            raise ValueError('Reply triggers must be unique')
        if self.welcome is not None and not self.welcome.strip():
            raise ValueError('Welcome must not be blank')
        return self


@dataclass(frozen=True)
class Template:
    id: str
    category: str
    title_ar: str
    title_en: str
    mode: Literal['welcome', 'message', 'command']
    version: int = 1

    def build(self, options: TemplateOptions) -> WorkflowDefinition:
        if self.mode == 'welcome' and options.rules:
            raise ValueError('Welcome template does not accept reply rules')
        if self.mode != 'welcome' and not options.rules:
            raise ValueError('This template requires at least one reply rule')
        nodes = [{'id': 'start', 'type': 'trigger.command', 'config': {'command': 'start'}},
                 {'id': 'welcome', 'type': 'action.message', 'config': {'text': options.welcome or (
                     'أهلًا بك 👋' if options.language_code == 'ar' else 'Welcome 👋')}}]
        edges = [{'source': 'start', 'target': 'welcome'}]
        for index, rule in enumerate(options.rules):
            trigger = rule.trigger
            if self.mode == 'command':
                import re
                if not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', trigger) or trigger == 'start':
                    raise ValueError('Commands must use lowercase ASCII, digits or _, excluding start')
            elif trigger.startswith('/'):
                raise ValueError('Message triggers cannot start with /; use the command template')
            node_id = f'rule_{index}'
            config = {'command': trigger} if self.mode == 'command' else {'text': trigger}
            nodes.extend([
                {'id': node_id, 'type': 'trigger.' + self.mode, 'config': config},
                {'id': f'reply_{index}', 'type': 'action.message', 'config': {'text': rule.response}},
            ])
            edges.append({'source': node_id, 'target': f'reply_{index}'})
        return WorkflowDefinition.model_validate({'nodes': nodes, 'edges': edges})


CATALOG = (
    Template('welcome', 'communication', 'بوت ترحيب', 'Welcome bot', 'welcome'),
    Template('auto-replies', 'communication', 'ردود نصية تلقائية', 'Text auto replies', 'message'),
    Template('command-menu', 'utilities', 'قائمة أوامر', 'Command menu', 'command'),
)


def get_template(template_id: str) -> Template:
    for template in CATALOG:
        if template.id == template_id:
            return template
    raise KeyError(template_id)
