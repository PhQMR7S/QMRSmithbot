"""Purpose-specific child-bot workspaces; every indicator comes from stored state."""
from sqlalchemy import func, select

from qmrsmithbot.db.factory_models import (
    BotFormSubmissionRecord,
    ContactBlockRecord,
    ContactDeliveryRecord,
    FactoryButtonRecord,
)
from qmrsmithbot.factory.menu import MenuState
from qmrsmithbot.telegram.inline_runtime import compile_text_program


async def child_dashboard(manager,menu,action):
    project_id=manager.store.project_id
    if action not in ('project:'+str(project_id),'workspace','delivery','identity','insights'):
        return None
    project=await manager.project(project_id)
    version=await manager.latest(project_id)
    program=compile_text_program(version.definition)
    await menu.save_state(MenuState('idle',{}))
    tr=lambda ar,en: ar if menu.lang=='ar' else en
    def button(ar,en,target,style=None):
        return {'text':tr(ar,en),'callback_data':target,**({'style':style} if style else {})}
    raw=str(project_id)
    root=button('لوحة البوت','Bot dashboard','project:'+raw)
    kind={'buttons':tr('مكتبة وأزرار','Library & buttons'),'contact':tr('تواصل خاص','Private contact'),
          'form':tr('نماذج تفاعلية','Interactive forms'),'text':tr('ردود وأوامر','Replies & commands')}[program.kind]
    status=tr('استقبال الزوار مفعّل','Visitor reception enabled') if project.status=='running' else tr('استقبال الزوار متوقف','Visitor reception paused')
    if action=='workspace':
        if program.kind=='buttons':
            rows=[[button('الأقسام والأزرار والملفات','Sections, buttons & files','buttons:'+raw,'primary')]]
            detail=tr('أنشئ أقسامًا متداخلة، ارفع الملفات من هنا، وغيّر ترتيب الأزرار وألوانها وصفوفها من تفاصيل كل زر.',
                      'Build nested sections, upload files here, and adjust each button’s order, color and row layout.')
        elif program.kind=='form':
            rows=[[button('مصمم الأسئلة والتفرعات','Question & branch designer','fe:home','primary')],
                  [button('صندوق الإجابات','Submission inbox',f'forms:{raw}:0')]]
            detail=tr('أنشئ الأسئلة والخيارات، اضبط الحدود والمسارات، وراجع الإجابات المكتملة. لا تحتاج مغادرة هذا البوت لتحرير النموذج.',
                      'Create questions and choices, configure limits and paths, and review submissions without leaving this bot.')
        elif program.kind=='contact':
            rows=[[button('إعداد استقبال الرسائل','Message reception setup','contactsetup:'+raw,'primary')]]
            detail=tr('رسائل الزوار تصل إلى هذه المحادثة. استخدم «رد» للإجابة؛ الحظر وإلغاء الحظر من أزرار الرسالة. لا تُرسل رسالتك إلى زائر دون رد مرتبط.',
                      'Visitor messages arrive in this chat. Reply to answer; use message controls to block/unblock. Unrelated owner messages are not forwarded.')
        else:
            rows=[[button('محرر الردود والأوامر','Reply & command editor','content:'+raw,'primary')]]
            detail=tr('أضف كل رد أو أمر على حدة، وعدّله وعاينه قبل النشر. المطابقة نصية ولا تتطلب مزود ذكاء اصطناعي.',
                      'Add, edit and preview replies or commands individually. Exact text matching needs no AI provider.')
        rows.append([button('النصوص الجاهزة','Prepared text library','copy:home')])
        rows += [[button('رسالة البداية','Welcome message','welcome:'+raw),button('معاينة المسودة','Preview draft','preview:'+raw)],[root]]
        return menu.response(tr('مساحة التحرير','Editing workspace')+'\n'+kind+'\n\n'+detail,rows)
    if action=='delivery':
        pending=version.version!=project.active_version
        if program.kind=='buttons':
            pending=pending or bool(await manager.session.scalar(select(FactoryButtonRecord.id).where(
                FactoryButtonRecord.project_id==project_id,
                ((FactoryButtonRecord.deleted.is_(False)) & FactoryButtonRecord.draft.is_distinct_from(FactoryButtonRecord.published)) |
                ((FactoryButtonRecord.deleted.is_(True)) & FactoryButtonRecord.published.is_not(None))).limit(1)))
        detail=status+tr(f'\nالمنشور: {project.active_version or "—"} · المسودة: {version.version}',
                        f'\nPublished: {project.active_version or "—"} · Draft: {version.version}')
        detail+='\n'+tr('توجد تغييرات غير منشورة' if pending else 'المسودة مطابقة للمنشور',
                         'Unpublished changes exist' if pending else 'Draft matches published content')
        detail+=tr('\n\nالنشر يطبّق المسودة على الزوار. إيقاف الاستقبال يبقي لوحة الإدارة متاحة لك.',
                   '\n\nPublishing applies the draft to visitors. Pausing reception keeps your dashboard accessible.')
        return menu.response(tr('النشر والتشغيل','Publishing & operation')+'\n\n'+detail,
            [[button('مراجعة ونشر المسودة','Review & publish','launchask:'+raw,'success')],
             [button('إيقاف الاستقبال' if project.status=='running' else 'استئناف الاستقبال',
                     'Pause reception' if project.status=='running' else 'Resume reception',
                     'stopask:'+raw if project.status=='running' else 'resumeask:'+raw)],
             [button('فحص الاتصال','Check connection','health:'+raw)],[root]])
    if action=='identity':
        return menu.response(tr('هوية البوت وإعداداته\n\nلوحتك خاصة بهذا البوت. تغييرات ملف تيليجرام تطبّق مباشرة؛ المحتوى يبقى مسودة حتى النشر.',
            'Bot identity & settings\n\nThis panel controls this bot only. Telegram profile changes apply immediately; content remains a draft until published.'),
            [[button('اسم العرض','Display name','profile:name:'+raw),button('وصف البوت','Description','profile:description:'+raw)],
             [button('النبذة المختصرة','Short bio','profile:about:'+raw),button('اسم المشروع','Project name','rename:'+raw)],
             [button('لوحات برسائل غنية','Rich management panels','display:rich'),button('عرض نصي بسيط','Plain panels','display:plain')],
             [button('ميزات تيليجرام المتاحة','Telegram feature availability','features')],
             [root]])
    if action=='insights':
        if program.kind=='form':
            count=await manager.session.scalar(select(func.count()).select_from(BotFormSubmissionRecord).where(BotFormSubmissionRecord.project_id==project_id))
            detail=tr(f'الأسئلة في المسودة: {len(program.form.questions)}\nالإجابات المكتملة المحفوظة: {count}',
                      f'Draft questions: {len(program.form.questions)}\nStored completed submissions: {count}')
        elif program.kind=='contact':
            visitors=await manager.session.scalar(select(func.count(func.distinct(ContactDeliveryRecord.visitor_id))).where(ContactDeliveryRecord.project_id==project_id))
            blocked=await manager.session.scalar(select(func.count()).select_from(ContactBlockRecord).where(ContactBlockRecord.project_id==project_id,ContactBlockRecord.blocked.is_(True)))
            detail=tr(f'مرسلون لديهم رسائل مرتبطة محفوظة: {visitors}\nمحظورون حاليًا: {blocked}',
                      f'Senders with stored delivery mappings: {visitors}\nCurrently blocked: {blocked}')
        elif program.kind=='buttons':
            counts=(await manager.session.execute(select(FactoryButtonRecord.draft['kind'].astext.label('kind'),func.count()).where(FactoryButtonRecord.project_id==project_id,FactoryButtonRecord.deleted.is_(False)).group_by('kind'))).all()
            detail=tr('عناصر المسودة المحفوظة','Saved draft items')+'\n'+'\n'.join(f'{tr({"section":"أقسام","text":"نصوص","url":"روابط","file":"ملفات"}.get(kind,kind),kind)}: {count}' for kind,count in counts)
        else:
            detail=tr(f'الردود: {len(program.messages)}\nالأوامر: {len(program.commands)-1}',
                      f'Replies: {len(program.messages)}\nCommands: {len(program.commands)-1}')
        return menu.response(tr('ملخص البوت','Bot overview')+'\n\n'+detail+'\n\n'+tr('الأرقام من البيانات المحفوظة، وليست قياسًا لكل الزيارات أو للسرعة.','Counts reflect stored data, not all visits or response latency.'),[[root]])
    return menu.response(project.name+'\n'+kind+'\n\n'+status+tr(
        f'\nالنسخة المنشورة: {project.active_version or "—"} · آخر مسودة: {version.version}\n\nمسار تجهيز بوتك مكتمل. اختر مساحة العمل المطلوبة؛ كل أداة هنا تخص هذا البوت فقط.',
        f'\nPublished: {project.active_version or "—"} · Latest draft: {version.version}\n\nYour setup path is complete. Choose a workspace; every tool here is scoped to this bot.'),
        [[button('تحرير المحتوى','Edit content','workspace','primary')],
         [button('النشر والتشغيل','Publishing & operation','delivery'),button('ملخص البوت','Bot overview','insights')],
         [button('الهوية والإعدادات','Identity & settings','identity')]])
