"""Native form setup and owner-only paginated submission review."""
from uuid import UUID, uuid4

from sqlalchemy import select

from qmrsmithbot.auth.models import Permission
from qmrsmithbot.config import settings
from qmrsmithbot.db.factory_models import BotFormSubmissionRecord
from qmrsmithbot.db.models import BotProjectRecord
from qmrsmithbot.factory.menu import MenuState
from qmrsmithbot.telegram.inline_runtime import InlineBotError, compile_text_program


class FormManager:
    def __init__(self, manager, menu):
        self.manager,self.menu,self.session=manager,menu,manager.session

    def tr(self,ar,en):
        return ar if self.menu.lang=='ar' else en

    def button(self,ar,en,data):
        return {'text':self.tr(ar,en),'callback_data':data}

    def back(self,project_id):
        return [self.button('↩ لوحة البوت','↩ Bot panel','project:'+str(project_id))]

    async def project(self,project_id,write=False):
        project=await self.manager.project(project_id,Permission.PROJECT_WRITE if write else Permission.PROJECT_READ,lock=write)
        if project.owner_id!=self.manager.store.user.id:
            raise InlineBotError('missing')
        program=compile_text_program((await self.manager.latest(project_id)).definition)
        if program.kind!='form':
            raise InlineBotError('missing')
        return project,program

    async def listing(self,project_id,offset=0):
        await self.project(project_id)
        records=(await self.session.scalars(select(BotFormSubmissionRecord).where(
            BotFormSubmissionRecord.project_id==project_id).order_by(
                BotFormSubmissionRecord.created_at.desc(),BotFormSubmissionRecord.id.desc()).offset(offset).limit(6))).all()
        rows=[[{'text':f'{r.data["title"][:35]} · {r.visitor_id}', 'callback_data':f'fs:{r.id.hex}:0'}] for r in records[:5]]
        pager=[]
        if offset:
            pager.append(self.button('السابق','Previous',f'forms:{project_id}:{max(0,offset-5)}'))
        if len(records)>5:
            pager.append(self.button('التالي','Next',f'forms:{project_id}:{offset+5}'))
        if pager:
            rows.append(pager)
        rows.append(self.back(project_id))
        return self.menu.response(self.tr('صندوق إجابات النماذج\n\nاختر إجابة مكتملة لمراجعتها.' if records else 'صندوق النماذج فارغ حتى الآن.',
            'Form submissions\n\nChoose a completed submission.' if records else 'No completed submissions yet.'),rows)

    async def record(self,item_id,write=False):
        record=await self.session.scalar(select(BotFormSubmissionRecord).join(BotProjectRecord,
            BotProjectRecord.id==BotFormSubmissionRecord.project_id).where(
                BotFormSubmissionRecord.id==item_id,BotProjectRecord.tenant_id==self.manager.store.tenant_id))
        if record is None:
            raise InlineBotError('missing')
        await self.project(record.project_id,write)
        return record

    async def handle(self,callback):
        if not callback:
            return None
        parts=callback.split(':')
        if parts[0]=='formsetup' and len(parts)==2:
            project_id=UUID(parts[1])
            _,program=await self.project(project_id)
            rows=[[self.button('الإجابات المكتملة','Completed submissions',f'forms:{project_id}:0')],
                [self.button('نشر وتشغيل','Publish & run',f'launchask:{project_id}')],self.back(project_id)]
            if settings.telegram_ingress_base_url:
                rows.insert(0,[{'text':self.tr('تصميم الأسئلة والتفرعات','Design questions & branches'),
                    'url':settings.telegram_ingress_base_url.rstrip('/')+'/dashboard?project='+str(project_id)}])
            return self.menu.response(program.form.title+'\n\n'+self.tr(
                f'عدد الأسئلة: {len(program.form.questions)}\n\nتدعم الأسئلة النصوص والأرقام والاختيارات. كل اختيار يمكنه الانتقال لسؤال لاحق أو إنهاء النموذج. الإجابات لا تظهر إلا لصاحب المشروع.\nتعديلات الأسئلة مسودات حتى النشر؛ الجلسات التي بدأت تكمل نسختها الأصلية.',
                f'Questions: {len(program.form.questions)}\n\nText, number and choice questions. Choices may branch to later questions or finish. Only the project owner can review answers.\nEdits stay drafts until publication; existing sessions keep their original questions.'),rows)
        if parts[0]=='forms' and len(parts)==3:
            offset=int(parts[2])
            if not 0<=offset<=2**31-1:
                raise ValueError()
            return await self.listing(UUID(parts[1]),offset)
        if parts[0]=='fs' and len(parts)==3:
            record=await self.record(UUID(parts[1]))
            index=int(parts[2])
            answers=record.data['answers']
            if not 0<=index<len(answers):
                raise ValueError()
            entry=answers[index]
            answer=entry['answer'] if entry['answer'] is not None else self.tr('تم التخطي','Skipped')
            body=f'{record.data["title"]}\nTelegram ID: {record.visitor_id}\n{index+1}/{len(answers)}\n\n{entry["question"]}\n\n{answer}'
            pager=[]
            if index:
                pager.append(self.button('السابق','Previous',f'fs:{record.id.hex}:{index-1}'))
            if index+1<len(answers):
                pager.append(self.button('التالي','Next',f'fs:{record.id.hex}:{index+1}'))
            return self.menu.response(body,([pager] if pager else [])+[
                [self.button('حذف الإجابة المكتملة','Delete submission','fdel:'+record.id.hex)],
                [self.button('صندوق الإجابات','Submissions',f'forms:{record.project_id}:0')]])
        if parts[0]=='fdel' and len(parts)==2:
            record=await self.record(UUID(parts[1]),True)
            nonce=uuid4().hex
            await self.menu.save_state(MenuState('form_delete',{'id':str(record.id),'nonce':nonce}))
            return self.menu.response(self.tr('حذف هذه الإجابة المكتملة نهائيًا؟','Permanently delete this submission?'),
                [[self.button('تأكيد الحذف','Confirm deletion','fdelok:'+nonce)],self.back(record.project_id)])
        if parts[0]=='fdelok' and len(parts)==2:
            state=await self.manager.store.state()
            if state.step!='form_delete' or state.data.get('nonce')!=parts[1]:
                return self.menu.response(self.menu.text('invalid'))
            record=await self.record(UUID(state.data['id']),True)
            project_id=record.project_id
            await self.session.delete(record)
            await self.manager.store.audit('factory.form.submission_deleted',project_id,
                self.manager.store.user.id,self.manager.store.tenant_id)
            await self.menu.save_state(MenuState('idle',{}))
            return await self.listing(project_id)
        return None
