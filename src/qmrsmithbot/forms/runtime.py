"""Transactional form progress; outbound Telegram commands follow the DB commit."""
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from qmrsmithbot.db.factory_models import BotFormSessionRecord, BotFormSubmissionRecord
from qmrsmithbot.forms.schema import Form, validate_answer


def say(actor_id, text, rows=None):
    result = {'method':'sendMessage','chat_id':actor_id,'text':text}
    if rows:
        result['reply_markup']={'inline_keyboard':rows}
    return result


def button(text, data):
    return {'text':text,'callback_data':data}


def prompt(actor_id, state, prefix=''):
    form=Form.model_validate(state['form'])
    question=next(q for q in form.questions if q.id==state['question'])
    index=next(i for i,q in enumerate(form.questions) if q.id==question.id)
    nonce=state['nonce']
    rows=[[button(c.label,f'f:{nonce}:{question.id}:{i}')] for i,c in enumerate(question.choices)]
    if not question.required:
        rows.append([button('تخطي | Skip',f'f:{nonce}:{question.id}:skip')])
    rows.append([button('إلغاء | Cancel',f'f:cancel:{nonce}')])
    return say(actor_id,prefix+f'{form.title}\n{index+1}/{len(form.questions)}\n\n'+question.prompt,rows)


async def _form_response(session, project, program, update):
    callback=update.callback_query
    message=callback.message if callback else update.message
    actor=callback.from_user if callback else message.from_user if message else None
    if (message is None or actor is None or actor.is_bot or actor.id<=0
            or message.chat.type!='private' or message.chat.id!=actor.id):
        return None
    if callback and (not getattr(message,'from_user',None) or message.from_user.id!=project.telegram_bot_id):
        return None
    now=datetime.now(UTC)
    record=await session.get(BotFormSessionRecord,(project.id,actor.id))
    expired=record is not None and record.expires_at<=now
    if expired:
        await session.delete(record)
        await session.flush()
        record=None
    if record is not None:
        record.expires_at=now+timedelta(minutes=30)
    text=message.text if not callback else None
    data=callback.data if callback else None
    command=text.split()[0].split('@')[0] if text and text.startswith('/') else None
    if command=='/cancel' or (data and data.startswith('f:cancel:')):
        if data and (record is None or data!='f:cancel:'+record.data['nonce']):
            return say(actor.id,'هذا الزر قديم. أرسل /start للمتابعة.')
        if record is not None:
            await session.delete(record)
        return say(actor.id,'تم إلغاء النموذج. لم تُحفظ إجابة مكتملة. /start للبدء من جديد.')
    if command=='/restart':
        if record is not None:
            await session.delete(record)
            await session.flush()
            record=None
        command='/start'
    if command=='/start':
        if record is not None:
            return prompt(actor.id,record.data,'عندك نموذج قيد الإجابة. /restart للبدء من جديد أو /cancel للإلغاء.\n\n')
        return say(actor.id,program.commands['start'],[[button('بدء النموذج | Start',f'f:start:{project.active_version}')]])
    if data and data.startswith('f:start:'):
        if data!=f'f:start:{project.active_version}':
            return say(actor.id,'تحدّث النموذج. أرسل /start لفتح النسخة الحالية.')
        if record is not None:
            return prompt(actor.id,record.data)
        form=program.form
        state={'form':form.model_dump(mode='json'),'question':form.questions[0].id,
            'answers':[],'nonce':uuid4().hex[:16],'version':project.active_version}
        record=BotFormSessionRecord(project_id=project.id,visitor_id=actor.id,data=state,
            expires_at=now+timedelta(minutes=30))
        session.add(record)
        return prompt(actor.id,state)
    if record is None:
        return say(actor.id,'انتهت الجلسة. أرسل /start للبدء من جديد.' if expired else 'أرسل /start لفتح النموذج.') if text or data else None
    state=dict(record.data)
    form=Form.model_validate(state['form'])
    question=next(q for q in form.questions if q.id==state['question'])
    choice_index=None
    answer=None
    if data:
        prefix=f'f:{state["nonce"]}:{question.id}:'
        if not data.startswith(prefix):
            return prompt(actor.id,state,'هذا الزر لا يخص السؤال الحالي.\n\n')
        value=data[len(prefix):]
        if value=='skip' and not question.required:
            answer=None
        elif question.kind=='choice' and len(value)==1 and value.isascii() and value.isdigit() and 0<=int(value)<len(question.choices):
            choice_index=int(value)
            answer=question.choices[choice_index].label
        else:
            return prompt(actor.id,state,'اختيار غير صالح.\n\n')
    elif command:
        return prompt(actor.id,state,'استخدم /cancel للإلغاء أو /restart لإعادة البدء.\n\n')
    elif question.kind=='choice':
        return prompt(actor.id,state,'اختر إجابتك من الأزرار.\n\n')
    else:
        if not text or re.search(r'\b[0-9]{5,16}:[A-Za-z0-9_-]{20,}\b',text):
            return prompt(actor.id,state,'أرسل إجابة نصية دون توكنات أو بيانات دخول.\n\n')
        try:
            answer=validate_answer(question,text)
        except ValueError as exc:
            return prompt(actor.id,state,str(exc)+'\n\n')
    answers=[*state['answers'],{'question_id':question.id,'question':question.prompt,'answer':answer}]
    target=form.after(question.id,choice_index)
    if target is None:
        session.add(BotFormSubmissionRecord(id=uuid4(),project_id=project.id,visitor_id=actor.id,
            version=state['version'],data={'title':form.title,'answers':answers}))
        await session.delete(record)
        return say(actor.id,form.completion,[[button('نموذج جديد | New form',f'f:start:{project.active_version}')]])
    record.data={**state,'question':target,'answers':answers}
    record.expires_at=now+timedelta(minutes=30)
    return prompt(actor.id,record.data)


async def form_response(session, project, program, update):
    response=await _form_response(session,project,program,update)
    callback=update.callback_query
    # Choice navigation updates the bot's own prompt instead of flooding the chat.
    # _form_response has already validated the private actor and message author.
    if response is not None and callback and getattr(callback.message,'text',None):
        response={**response,'method':'editMessageText','message_id':callback.message.message_id}
    return response
