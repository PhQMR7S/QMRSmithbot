from types import SimpleNamespace
from uuid import uuid4

from aiogram.types import InlineKeyboardMarkup

from qmrsmithbot.factory.menu import FactoryMenu, MenuState
from qmrsmithbot.factory.project_hub import project_hub
from qmrsmithbot.factory.starters import STARTERS, starter_records
from qmrsmithbot.telegram.inline_runtime import compile_text_program
from qmrsmithbot.templates.catalog import TemplateOptions, get_template


class Store:
    def __init__(self):
        self.lang = 'ar'
        self.conversation = MenuState('idle', {})
        self.created = []

    async def language(self):
        return self.lang

    async def state(self):
        return self.conversation

    async def save_state(self, state):
        self.conversation = state



async def test_preview_navigates_without_creating_and_retains_selection_in_review():
    store = Store()
    menu = FactoryMenu(store, telegram_id=42)
    for lang in ('ar','en'):
        store.lang = lang
        response = await menu.handle(callback='discover:buttons')
        InlineKeyboardMarkup.model_validate(response['reply_markup'])
        await menu.handle(callback='starters')
        await menu.handle(callback='starter:knowledge')
        root = await menu.handle(callback='sdemo:knowledge:root')
        section = await menu.handle(callback='sdemo:knowledge:0')
        leaf = await menu.handle(callback='sdemo:knowledge:1')
        assert root['text'] != section['text'] != leaf['text']
        assert not store.created
        await menu.handle(callback='suse:knowledge')
        assert store.conversation.data['starter'] == 'knowledge'
        await menu.handle(text='My library')
        review = await menu.handle(callback='wizarddefault')
        assert store.conversation.data['starter'] == 'knowledge'
        assert 'sample' in review['text'] if lang == 'en' else 'النموذجية' in review['text']
        await menu.handle(text='/cancel')
        assert 'starter' not in store.conversation.data
        for bad in ('sdemo:knowledge:-1','sdemo:knowledge:999','sdemo:knowledge:x','starter:unknown','suse:unknown'):
            result=await menu.handle(callback=bad)
            assert result['text']==menu.text('invalid')


def test_starter_copies_have_independent_ids_valid_parents_and_stable_order():
    project_a,project_b=uuid4(),uuid4()
    for starter in STARTERS:
        first=starter_records(starter.id,project_a,'ar')
        second=starter_records(starter.id,project_b,'en')
        ids={item.id for item in first}
        assert not ids.intersection(item.id for item in second)
        assert all(item.project_id==project_a and item.published is None for item in first)
        assert all(item.parent_id is None or item.parent_id in ids for item in first)
        assert [r.created_at for r in first]==sorted(r.created_at for r in first)
        assert len({r.created_at for r in first})==len(first)


def test_hub_gives_actionable_upload_guidance_and_type_specific_controls():
    project=SimpleNamespace(id=uuid4(),name='Library',telegram_username=None,
        telegram_bot_id=None,active_version=None,status='draft')
    for kind in ('buttons','contact','form','welcome'):
        program=compile_text_program(get_template(kind).build(TemplateOptions()).model_dump(mode='json'))
        text,rows=project_hub(project=project,version=SimpleNamespace(version=2),program=program,
            record=None,pending=True,language='en',counts={'file':2,'missing_file':2},studio_url='')
        assert 'Connect your bot' in text
        assert 'not reached visitors' in text
        assert not any('url' in b for row in rows for b in row)
        if kind=='buttons':
            assert 'awaiting upload: 2' in text
        InlineKeyboardMarkup.model_validate({'inline_keyboard':rows})
