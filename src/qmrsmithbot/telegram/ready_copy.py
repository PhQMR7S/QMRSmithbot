"""Prepared bilingual copy, adapted to real template capabilities."""
import secrets
from copy import deepcopy
from dataclasses import dataclass
from uuid import uuid4

from qmrsmithbot.auth.models import Permission
from qmrsmithbot.db.factory_models import FactoryButtonRecord
from qmrsmithbot.factory.menu import MenuState
from qmrsmithbot.forms.schema import Form
from qmrsmithbot.telegram.inline_runtime import InlineBotError, compile_text_program


@dataclass(frozen=True)
class CopyOption:
    id: str
    label: tuple[str,str]
    target: str
    text: str


def prepared_copy(kind,name,language='ar'):
    ar=language=='ar'
    title=name.strip()[:120]
    instructions={
        'buttons':('تصفّح الأقسام من الأزرار أدناه، ثم اختر المحتوى أو الملف الذي تحتاجه. يمكنك العودة إلى القائمة الرئيسية في أي وقت.',
                   'Browse the buttons below, then choose the content or file you need. You can return to the main menu at any time.'),
        'contact':('أرسل رسالتك أو مرفقك هنا ليصل إلى صاحب البوت. اشرح طلبك في رسالة واضحة، ولا ترسل كلمات المرور أو رموز تسجيل الدخول. سيصلك الرد في هذه المحادثة عندما يجيب صاحب البوت.',
                   'Send your message or attachment here to reach the bot owner. Describe your request clearly and do not share passwords or login codes. Replies arrive in this chat when the owner responds.'),
        'form':('اضغط «ابدأ» وأجب عن الأسئلة بالترتيب. يمكنك تخطي السؤال الاختياري أو إرسال /cancel لإلغاء الإجابات غير المكتملة. لا تدخل كلمات المرور أو رموز تسجيل الدخول.',
                'Press Start and answer the questions in order. Optional questions can be skipped. Send /cancel to discard an unfinished response. Do not enter passwords or login codes.'),
        'text':('أرسل العبارة أو الأمر الذي ترغب باستخدامه. الردود هنا معدّة مسبقًا؛ إذا لم تجد ردًا مطابقًا، جرّب العبارة أو الأمر الذي حدده صاحب البوت.',
                'Send the phrase or command you want to use. Responses are predefined; if there is no match, try the wording or command provided by the bot owner.'),
    }
    hint=instructions.get(kind,instructions['text'])[0 if ar else 1]
    greeting=f'أهلًا بك في {title}.\n\n' if ar else f'Welcome to {title}.\n\n'
    result=[CopyOption('welcome',('ترحيب واضح ومتكامل','Complete welcome'),'welcome',greeting+hint),
            CopyOption('short',('ترحيب مختصر','Short welcome'),'welcome',
                greeting+hint.split('. ')[0].rstrip('.')+'.'),
            CopyOption('formal',('ترحيب رسمي','Formal welcome'),'welcome',
                (f'مرحبًا بكم في {title}.\nنسعد باستخدامكم لهذه الخدمة.\n\n' if ar else f'Welcome to {title}.\nThank you for using this service.\n\n')+hint)]
    if kind=='form':
        result.append(CopyOption('complete',('تأكيد حفظ الإجابات','Submission confirmation'),'completion',
            'تم حفظ إجاباتك بنجاح. شكرًا لوقتك. يمكنك إرسال /start لبدء نموذج جديد. لا تعني هذه الرسالة قبول الطلب أو تحديد موعد للرد.' if ar else
            'Your answers have been saved. Thank you for your time. Send /start to begin a new form. This confirms receipt, not approval or a promised response time.'))
    if kind=='buttons':
        result.append(CopyOption('guide',('زر دليل الاستخدام','Usage guide button'),'button',hint+('\n\nلإعادة فتح القائمة، أرسل /start.' if ar else '\n\nSend /start to reopen the menu.')))
    return result


async def ready_copy_panel(manager,menu,action):
    if not action or not action.startswith('copy:'):
        return None
    tr=lambda ar,en: ar if menu.lang=='ar' else en
    project_id=manager.store.project_id
    project=await manager.project(project_id,Permission.PROJECT_WRITE,lock=True)
    version=await manager.latest(project_id)
    program=compile_text_program(version.definition)
    options=prepared_copy(program.kind,project.name,menu.lang)
    def button(ar,en,data):
        return {'text':tr(ar,en),'callback_data':data}
    if action=='copy:home':
        await menu.save_state(MenuState('idle',{}))
        return menu.response(tr('مكتبة النصوص الجاهزة\n\nاختر نصًا لمعاينته. النصوص مناسبة لنوع هذا البوت وتُحفظ كمسودة فقط. يمكنك تعديلها بعد التطبيق؛ لن تصل للزوار قبل النشر.',
            'Prepared text library\n\nChoose a text to preview. Copy is adapted to this bot type and saved only as a draft. Edit it after applying; visitors see it only after publication.'),
            [[button(option.label[0],option.label[1],'copy:preview:'+option.id)] for option in options]+[
                [button('مساحة التحرير','Editing workspace','workspace')]])
    parts=action.split(':')
    if len(parts)!=3:
        raise ValueError()
    if parts[1]=='preview':
        option=next((o for o in options if o.id==parts[2]),None)
        if option is None:
            raise ValueError()
        nonce=secrets.token_hex(12)
        await menu.save_state(MenuState('child_ready_copy',{'nonce':nonce,'version':version.version,
            'option':option.id,'text':option.text,'target':option.target}))
        return menu.response(tr('معاينة النص المقترح','Suggested text preview')+'\n\n'+option.text+'\n\n'+tr('التطبيق يستبدل حقل النص المختار في المسودة، أو يضيف زر دليل استخدام جديدًا.','Applying replaces the selected draft text field, or creates a new usage-guide button.'),
            [[button('تطبيق كمسودة','Apply as draft','copy:apply:'+nonce)],
             [button('العودة للنصوص','Back to text library','copy:home')]])
    if parts[1]!='apply':
        raise ValueError()
    state=await manager.store.state()
    if state.step!='child_ready_copy' or state.data.get('nonce')!=parts[2] or state.data.get('version')!=version.version:
        raise InlineBotError('stale')
    data=state.data
    if data['target']=='welcome':
        await manager.save_content(project_id,welcome=data['text'])
    elif data['target']=='completion' and program.kind=='form':
        definition=deepcopy(version.definition)
        raw=program.form.model_dump(mode='json')
        raw['completion']=data['text']
        definition['variables']['form']=Form.model_validate(raw).model_dump(mode='json')
        await manager.store.projects_service.save_version(project_id=project_id,
            tenant_id=manager.store.tenant_id,definition=definition)
    elif data['target']=='button' and program.kind=='buttons':
        manager.session.add(FactoryButtonRecord(id=uuid4(),project_id=project_id,parent_id=None,
            draft={'kind':'text','title':tr('دليل الاستخدام','Usage guide'),'text':data['text']},deleted=False))
        await manager.session.flush()
    else:
        raise ValueError()
    await manager.store.audit('child.ready_copy.applied',project_id,manager.store.user.id,manager.store.tenant_id)
    await menu.save_state(MenuState('idle',{}))
    return menu.response(tr('حُفظ النص كمسودة. راجعه أو عدّله ثم انشره عندما يكون مناسبًا لبوتك.','Text saved as a draft. Review or edit it, then publish when appropriate for your bot.'),
        [[button('النشر والتشغيل','Publishing & operation','delivery')],
         [button('مساحة التحرير','Editing workspace','workspace')]])
