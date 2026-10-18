"""Versioned conversational form designer operated entirely inside the child bot."""
import re
import secrets
from copy import deepcopy
from uuid import uuid4

from qmrsmithbot.auth.models import Permission
from qmrsmithbot.factory.menu import MenuState
from qmrsmithbot.forms.schema import Form
from qmrsmithbot.telegram.inline_runtime import InlineBotError, compile_text_program


class ChildFormEditor:
    def __init__(self,manager,menu):
        self.manager,self.menu=manager,menu
        self.project_id=manager.store.project_id

    def tr(self,ar,en):
        return ar if self.menu.lang=='ar' else en

    def button(self,ar,en,data):
        return {'text':self.tr(ar,en),'callback_data':data}

    async def current(self,expected=None):
        await self.manager.project(self.project_id,Permission.PROJECT_WRITE,lock=True)
        version=await self.manager.latest(self.project_id)
        program=compile_text_program(version.definition)
        if program.kind!='form':
            raise InlineBotError('missing')
        if expected is not None and expected!=version.version:
            raise InlineBotError('stale')
        return version,program.form

    async def persist(self,version,raw):
        form=Form.model_validate(raw)
        definition=deepcopy(version.definition)
        definition['variables']['form']=form.model_dump(mode='json')
        await self.manager.store.projects_service.save_version(project_id=self.project_id,
            tenant_id=self.manager.store.tenant_id,definition=definition)
        await self.manager.store.audit('child.form.edited',self.project_id,
            self.manager.store.user.id,self.manager.store.tenant_id)
        await self.menu.save_state(MenuState('idle',{}))

    async def home(self):
        version,form=await self.current()
        await self.menu.save_state(MenuState('idle',{}))
        rows=[[self.button(f'{i+1} · {q.prompt[:42]}',f'{i+1} · {q.prompt[:42]}',f'fe:q:{version.version}:{i}')] for i,q in enumerate(form.questions)]
        rows += [[self.button('سؤال نصي جديد','Add text',f'fe:add:{version.version}:text'),
                  self.button('سؤال رقمي جديد','Add number',f'fe:add:{version.version}:number')],
                 [self.button('سؤال اختيارات جديد','Add choices',f'fe:add:{version.version}:choice')],
                 [self.button('عنوان النموذج','Form title',f'fe:field:{version.version}:title'),
                  self.button('رسالة الإكمال','Completion message',f'fe:field:{version.version}:completion')],
                 [self.button('الإجابات المكتملة','Submissions',f'forms:{self.project_id}:0')],
                 [self.button('نشر المسودة','Publish draft','launchask:'+str(self.project_id))],
                 [self.button('لوحة البوت','Bot panel','project:'+str(self.project_id))]]
        return self.menu.response(form.title+'\n\n'+self.tr(
            f'مصمم النماذج · المسودة {version.version}\n{len(form.questions)} / 20 سؤالًا\n\nحرّر السؤال، نوعه وخياراته وحدوده ومساره. كل حفظ ينشئ مسودة؛ الزوار يكملون النسخة التي بدأوا بها حتى لو نشرت نسخة جديدة.',
            f'Form designer · Draft {version.version}\n{len(form.questions)} / 20 questions\n\nEdit prompts, choices, limits and paths. Each save creates a draft. Visitors keep the version they started.'),rows)

    async def question(self,index):
        version,form=await self.current()
        await self.menu.save_state(MenuState('idle',{}))
        if not 0<=index<len(form.questions):
            raise ValueError()
        q=form.questions[index]
        base=f'{version.version}:{index}'
        rows=[[self.button('نص السؤال','Question prompt','fe:prompt:'+base),
               self.button('جعله اختياريًا' if q.required else 'جعله مطلوبًا','Make optional' if q.required else 'Make required','fe:required:'+base)]]
        rows.append([self.button('نوع السؤال','Question type','fe:type:'+base)])
        if q.kind=='number':
            rows.append([self.button('الحدود الرقمية','Number limits','fe:limits:'+base)])
        if q.kind=='choice':
            rows.append([self.button('تعديل الخيارات','Edit choices','fe:choices:'+base)])
            rows += [[self.button('مسار · '+c.label[:35],'Path · '+c.label[:35],f'fe:branch:{base}:{i}')] for i,c in enumerate(q.choices)]
        rows += [[self.button('للأعلى','Move up','fe:up:'+base),self.button('للأسفل','Move down','fe:down:'+base)],
                 [self.button('حذف السؤال','Delete question','fe:delete:'+base)],
                 [self.button('كل الأسئلة','All questions','fe:home')]]
        detail=self.tr('مطلوب' if q.required else 'اختياري','Required' if q.required else 'Optional')
        detail+=' · '+{'text':self.tr('نصي','Text'),'number':self.tr('رقمي','Number'),'choice':self.tr('اختيارات','Choices')}[q.kind]
        if q.kind=='number':
            detail+=f'\n{q.minimum if q.minimum is not None else "—"} … {q.maximum if q.maximum is not None else "—"}'
        if q.kind=='choice':
            positions={item.id:i+1 for i,item in enumerate(form.questions)}
            for choice in q.choices:
                target=self.tr('إنهاء','Finish') if choice.next=='end' else str(positions[choice.next]) if choice.next else self.tr('التالي','Next')
                detail+='\n'+choice.label+' ← '+target
        return self.menu.response(self.tr(f'السؤال {index+1} / {len(form.questions)}',f'Question {index+1} / {len(form.questions)}')+'\n\n'+q.prompt+'\n\n'+detail,rows)

    async def handle(self,action=None,text=None):
        state=await self.manager.store.state()
        if text is not None and state.step=='child_form_input':
            data=state.data
            version,form=await self.current(data['version'])
            raw=form.model_dump(mode='json')
            if re.search(r'\b[0-9]{5,16}:[A-Za-z0-9_-]{20,}\b',text):
                raise ValueError('Credentials cannot be stored in form content')
            field=data['field']
            if field in ('title','completion'):
                raw[field]=text.strip()
            elif field=='add':
                if len(raw['questions'])>=20:
                    raise ValueError('Question limit')
                kind=data['kind']
                raw['questions'].append({'id':'q'+uuid4().hex[:12],'prompt':text.strip(),'kind':kind,
                    **({'choices':[{'label':self.tr('الخيار الأول','First option')},{'label':self.tr('الخيار الثاني','Second option')}]} if kind=='choice' else {})})
            else:
                q=raw['questions'][data['index']]
                if field=='prompt':
                    q['prompt']=text.strip()
                elif field=='limits':
                    values=text.strip().split()
                    if len(values)!=2:
                        raise ValueError('Provide minimum and maximum, using - for no limit')
                    q['minimum'],q['maximum']=[None if value=='-' else float(value) for value in values]
                elif field=='choices':
                    q['choices']=[{'label':line.strip()} for line in text.splitlines() if line.strip()]
                else:
                    raise ValueError('Invalid form edit')
            await self.persist(version,raw)
            return await self.home()
        if not action or not action.startswith('fe:'):
            return None
        parts=action.split(':')
        if action=='fe:home':
            return await self.home()
        if len(parts)<4:
            raise ValueError()
        operation=parts[1]
        lengths={'q':4,'field':4,'add':4,'prompt':4,'limits':4,'choices':4,'required':4,'up':4,'down':4,'delete':4,'remove':5,'branch':5,'target':6,'type':4,'settype':5}
        if len(parts)!=lengths.get(operation):
            raise ValueError()
        version,form=await self.current(int(parts[2]))
        raw=form.model_dump(mode='json')
        if operation in ('field','add'):
            field=parts[3]
            if (operation=='field' and field not in ('title','completion')) or (operation=='add' and field not in ('text','number','choice')):
                raise ValueError()
            await self.menu.save_state(MenuState('child_form_input',{'version':version.version,
                'field':field if operation=='field' else 'add','kind':field}))
            return self.menu.response(self.tr('أرسل النص الجديد. عنوان النموذج حتى 100 حرف، رسالة الإكمال حتى 1000 حرف، ونص السؤال حتى 500 حرف. /cancel للعودة.',
                'Send the new text: title up to 100, completion up to 1000, or question up to 500 characters. /cancel to return.'),[[self.button('إلغاء','Cancel','fe:home')]])
        index=int(parts[3])
        if not 0<=index<len(form.questions):
            raise ValueError()
        if operation=='q':
            return await self.question(index)
        q=raw['questions'][index]
        if operation in ('prompt','limits','choices'):
            await self.menu.save_state(MenuState('child_form_input',{'version':version.version,'index':index,'field':operation}))
            prompt={'prompt':self.tr('أرسل نص السؤال الجديد، حتى 500 حرف.','Send the question prompt, up to 500 characters.'),
                    'limits':self.tr('أرسل الحد الأدنى والأعلى وبينهما مسافة، مثل: 18 65\nاستخدم - لغياب الحد، مثل: 18 -','Send minimum and maximum separated by a space, e.g. 18 65. Use - for no bound: 18 -'),
                    'choices':self.tr('أرسل 2–8 خيارات، كل خيار بسطر (حتى 64 حرفًا). سيُعاد ضبط مسارات هذه الخيارات إلى «التالي»؛ يمكنك ضبطها مجددًا بعد الحفظ.',
                                     'Send 2–8 choices, one per line (up to 64 characters). Their paths reset to Next; configure them again after saving.')}[operation]
            if (operation=='limits' and q['kind']!='number') or (operation=='choices' and q['kind']!='choice'):
                raise ValueError()
            return self.menu.response(prompt,[[self.button('إلغاء','Cancel','fe:home')]])
        if operation=='type':
            await self.menu.save_state(MenuState('idle',{}))
            return self.menu.response(self.tr('اختر نوع السؤال. تغيير النوع يعيد ضبط خياراته وحدوده؛ يبقى النص كما هو.','Choose a question type. Changing it resets choices and number limits; the prompt is preserved.'),
                [[self.button('نصي','Text',f'fe:settype:{version.version}:{index}:text'),
                  self.button('رقمي','Number',f'fe:settype:{version.version}:{index}:number'),
                  self.button('اختيارات','Choices',f'fe:settype:{version.version}:{index}:choice')],
                 [self.button('رجوع','Back',f'fe:q:{version.version}:{index}')]])
        if operation=='settype':
            kind=parts[4]
            if kind not in ('text','number','choice'):
                raise ValueError()
            if kind==q['kind']:
                return await self.question(index)
            q.update(kind=kind,minimum=None,maximum=None,choices=[])
            if kind=='choice':
                q['choices']=[{'label':self.tr('الخيار الأول','First option')},{'label':self.tr('الخيار الثاني','Second option')}]
        elif operation=='required':
            q['required']=not q['required']
        elif operation in ('up','down'):
            target=index+(-1 if operation=='up' else 1)
            if not 0<=target<len(raw['questions']):
                return await self.question(index)
            raw['questions'][index],raw['questions'][target]=raw['questions'][target],raw['questions'][index]
            index=target
        elif operation=='delete':
            nonce=secrets.token_hex(12)
            await self.menu.save_state(MenuState('child_form_delete',{'version':version.version,'index':index,'nonce':nonce}))
            return self.menu.response(self.tr('حذف السؤال؟ لا يمكن حذف آخر سؤال أو سؤال تتجه إليه تفرعات. عدّل التفرعات أولًا.',
                'Delete this question? The last question and a question targeted by a branch cannot be deleted. Change incoming branches first.'),
                [[self.button('تأكيد الحذف','Confirm deletion',f'fe:remove:{version.version}:{index}:{nonce}')],
                 [self.button('إلغاء','Cancel',f'fe:q:{version.version}:{index}')]])
        elif operation=='remove':
            if state.step!='child_form_delete' or state.data.get('version')!=version.version or state.data.get('index')!=index or len(parts)!=5 or state.data.get('nonce')!=parts[4]:
                raise ValueError()
            if len(raw['questions'])==1 or any(c.next==q['id'] for question in form.questions for c in question.choices):
                raise ValueError('Change incoming branches before deletion')
            raw['questions'].pop(index)
            await self.persist(version,raw)
            return await self.home()
        elif operation=='branch':
            await self.menu.save_state(MenuState('idle',{}))
            choice=int(parts[4])
            if q['kind']!='choice' or not 0<=choice<len(q['choices']):
                raise ValueError()
            rows=[[self.button('التالي','Next',f'fe:target:{version.version}:{index}:{choice}:next'),
                   self.button('إنهاء النموذج','Finish',f'fe:target:{version.version}:{index}:{choice}:end')]]
            rows += [[self.button(f'{i+1} · {question.prompt[:35]}',f'{i+1} · {question.prompt[:35]}',f'fe:target:{version.version}:{index}:{choice}:{question.id}')] for i,question in enumerate(form.questions) if i>index]
            rows.append([self.button('رجوع','Back',f'fe:q:{version.version}:{index}')])
            return self.menu.response(self.tr('اختر وجهة هذا الخيار. يسمح بسؤال لاحق أو إنهاء النموذج.','Choose the destination: a later question or finish.'),rows)
        elif operation=='target':
            if len(parts)!=6 or q['kind']!='choice':
                raise ValueError()
            choice=int(parts[4])
            if not 0<=choice<len(q['choices']):
                raise ValueError()
            q['choices'][choice]['next']=None if parts[5]=='next' else parts[5]
        else:
            raise ValueError()
        await self.persist(version,raw)
        return await self.question(index)
