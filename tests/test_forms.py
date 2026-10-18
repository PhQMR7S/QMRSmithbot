from types import SimpleNamespace
from uuid import uuid4

import pytest
from aiogram.types import Update
from pydantic import ValidationError

from qmrsmithbot.forms.schema import Form, Question, default_form, validate_answer
from qmrsmithbot.telegram.inline_runtime import InlineBotError, compile_text_program
from qmrsmithbot.templates.catalog import TemplateOptions, get_template


def test_form_paths_are_forward_only_and_snapshots_compile():
    form=Form(title='Test',questions=[
        Question(id='first',prompt='Choose',kind='choice',choices=[
            {'label':'Skip ahead','next':'last'},{'label':'Finish','next':'end'}]),
        Question(id='middle',prompt='Middle'),Question(id='last',prompt='Last')])
    assert form.after('first',0)=='last'
    assert form.after('first',1) is None
    assert form.after('middle')=='last'
    definition=get_template('form').build(TemplateOptions()).model_dump(mode='json')
    definition['variables']['form']=form.model_dump(mode='json')
    assert compile_text_program(definition).form.title=='Test'
    definition['variables']['arbitrary_code']='untrusted'
    with pytest.raises(InlineBotError):
        compile_text_program(definition)


@pytest.mark.parametrize('target',['missing','first'])
def test_form_rejects_cycles_or_missing_targets(target):
    with pytest.raises(ValidationError):
        Form(title='Test',questions=[Question(id='first',prompt='Choose',kind='choice',choices=[
            {'label':'A','next':target},{'label':'B'}])])


@pytest.mark.parametrize('raw', [
    {'id':'q','prompt':' ','kind':'text'},
    {'id':'end','prompt':'Question'},
    {'id':'q','prompt':'Question','kind':'choice','choices':[{'label':'A'},{'label':' A '}]},
    {'id':'q','prompt':'Question','kind':'number','minimum':10,'maximum':2},
    {'id':'q','prompt':'Question','kind':'text','maximum':3},
])
def test_questions_reject_ambiguous_or_invalid_configuration(raw):
    with pytest.raises(ValidationError):
        Question.model_validate(raw)


@pytest.mark.parametrize('value',['NaN','Infinity','-Infinity','1e999999','1e9999999999999999999999999','17','1000000001','abc'])
def test_number_answer_is_bounded_and_safe(value):
    question=Question(id='age',prompt='Age',kind='number',minimum=18,maximum=90)
    with pytest.raises(ValueError):
        validate_answer(question,value)


def test_text_and_arabic_number_validation():
    assert validate_answer(Question(id='q',prompt='Age',kind='number'),'١٢')=='١٢'
    assert validate_answer(Question(id='q',prompt='Text'),'  name  ')=='name'
    with pytest.raises(ValueError):
        validate_answer(Question(id='q',prompt='Text'),'x'*1001)
    assert default_form('en').completion.startswith('✅')


@pytest.mark.asyncio
async def test_form_runtime_ignores_groups_and_forged_callback_authors():
    from qmrsmithbot.forms.runtime import form_response
    actor={'id':7,'is_bot':False,'first_name':'Test'}
    message={'message_id':1,'date':0,'chat':{'id':7,'type':'private'},'from':actor,'text':'menu'}
    update=Update.model_validate({'update_id':1,'callback_query':{'id':'a','from':actor,
        'chat_instance':'x','message':message,'data':'f:start:1'}})
    project=SimpleNamespace(id=uuid4(),telegram_bot_id=12345)
    assert await form_response(None,project,None,update) is None
    message['chat']={'id':-100,'type':'supergroup'}
    update=Update.model_validate({'update_id':2,'message':message})
    assert await form_response(None,project,None,update) is None
