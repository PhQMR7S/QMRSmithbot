from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from aiogram.types import InlineKeyboardMarkup
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from qmrsmithbot.api.studio import ButtonDraft
from qmrsmithbot.factory.button_design import append_visitor_button, order_expression, original_key


def test_layout_colors_and_three_button_cap():
    rows=[]
    for index in range(5):
        append_visitor_button(rows,{'kind':'text','title':str(index),'join_previous':True,
                                   'style':'success'},uuid4())
    assert [len(row) for row in rows]==[3,2]
    assert all(b['style']=='success' for row in rows for b in row)
    append_visitor_button(rows,{'kind':'url','title':'Website','url':'https://example.com',
                               'join_previous':False,'style':'not-allowed'},uuid4())
    assert len(rows[-1])==1 and 'style' not in rows[-1][0]
    InlineKeyboardMarkup.model_validate({'inline_keyboard':rows})


def test_api_rejects_arbitrary_styles_and_internal_order_fields():
    payload=ButtonDraft(kind='text',title='Test',text='Body',style='primary',join_previous=True)
    assert payload.content()['style']=='primary'
    assert payload.content()['join_previous'] is True
    assert ButtonDraft(kind='text',title='Test',text='Body').content()=={
        'kind':'text','title':'Test','text':'Body'}
    for extra in ({'style':'evil'},{'sort_key':'x'}):
        with pytest.raises(ValidationError):
            ButtonDraft(kind='text',title='Test',text='Body',**extra)


def test_original_order_key_keeps_old_chronology_and_separate_snapshots():
    item=SimpleNamespace(created_at=datetime(2026,10,18,1,2,3,456789,tzinfo=UTC),id=uuid4())
    assert original_key(item)=='20261018010203456789'+item.id.hex
    draft=str(order_expression().compile(dialect=postgresql.dialect()))
    live=str(order_expression('published').compile(dialect=postgresql.dialect()))
    assert 'factory_buttons.draft' in draft
    assert 'factory_buttons.published' in live
