"""A project-specific control center with actionable setup guidance."""


def project_hub(*, project, version, program, record, pending, language, counts, studio_url):
    tr = lambda ar, en: ar if language == 'ar' else en
    raw = str(project.id)
    def button(ar, en, action):
        return {'text':tr(ar,en), 'callback_data':action+':'+raw}
    connected = bool(project.telegram_bot_id)
    published = bool(project.active_version)
    kinds = {'buttons':tr('أزرار ومكتبة ملفات','Buttons & files'),
             'contact':tr('تواصل خاص','Private contact'), 'form':tr('نموذج تفاعلي','Interactive form')}
    title = kinds.get(program.kind, tr('ردود وأوامر','Replies & commands'))
    state = {'running':tr('يعمل','Running'), 'stopped':tr('متوقف','Stopped'),
             'draft':tr('مسودة','Draft'), 'error':tr('يحتاج مراجعة','Needs attention')}.get(project.status, project.status)
    body = [project.name, title+' · '+state,
            '@'+project.telegram_username if project.telegram_username else tr('لم يُربط حساب البوت بعد','Telegram bot not connected'),
            '', tr('مسار تجهيز بوتك','Your setup path'),
            tr('✓ المسودة جاهزة','✓ Draft created'),
            tr('✓ تم ربط البوت' if connected else '○ اربط البوت من قسم الاتصال',
               '✓ Bot connected' if connected else '○ Connect your bot in Connection'),
            tr('✓ توجد نسخة منشورة' if published else '○ انشر النسخة الأولى بعد مراجعة المحتوى',
               '✓ A version is published' if published else '○ Review content and publish the first version')]
    if pending:
        body.append(tr('○ لديك تعديلات لم تصل للزوار بعد','○ Draft changes have not reached visitors yet'))
    if program.kind == 'buttons':
        body += ['', tr('محتوى المسودة','Draft content'),
                 tr(f'الأقسام: {counts.get("section",0)} · النصوص: {counts.get("text",0)}',
                    f'Sections: {counts.get("section",0)} · Texts: {counts.get("text",0)}'),
                 tr(f'الروابط: {counts.get("url",0)} · الملفات: {counts.get("file",0)}',
                    f'Links: {counts.get("url",0)} · Files: {counts.get("file",0)}')]
        if counts.get('missing_file'):
            body.append(tr(f'ملفات تنتظر الرفع: {counts["missing_file"]}. انشر البوت لفتح الرفع، ثم انشر الملفات بعد استلامها.',
                           f'Files awaiting upload: {counts["missing_file"]}. Publish to enable uploads, then publish the received files.'))
        if not sum(counts.get(k,0) for k in ('section','text','url','file')):
            body.append(tr('قائمة الأزرار فارغة. ابدأ بإضافة قسم أو نص من محرر المحتوى.', 'The button menu is empty. Add a section or text in the content editor.'))
        editor = button('تحرير الأقسام والأزرار','Edit sections & buttons','buttons')
    elif program.kind == 'form':
        form = program.form
        body += ['',tr(f'الأسئلة: {len(form.questions)} · الإجابات محفوظة لصاحب البوت فقط',
                       f'Questions: {len(form.questions)} · Submissions are owner-only')]
        editor = button('تحرير الأسئلة والتفرعات','Edit questions & branches','formsetup')
    elif program.kind == 'contact':
        body += ['',tr('الزائر يراسلك داخل بوتك، وترد باستخدام «رد» على رسالته. يمكنك حظر المرسل وإلغاء حظره.',
                       'Visitors message you in your bot. Reply to their messages to answer; sender blocking is available.')]
        editor = button('إعداد التواصل والرسالة','Contact setup & greeting','contactsetup')
    else:
        body += ['',tr(f'الردود: {len(program.messages)} · الأوامر: {len(program.commands)-1}',
                       f'Replies: {len(program.messages)} · Commands: {len(program.commands)-1}')]
        editor = button('تحرير المحتوى والردود','Edit content & replies','content')
    body += ['',tr(f'المنشور: {project.active_version or "—"} · المسودة: {version.version}',
                   f'Published: {project.active_version or "—"} · Draft: {version.version}')]
    rows = [[editor],
            [button('رسالة البداية','Welcome message','welcome'),button('معاينة المسودة','Preview draft','preview')]]
    if studio_url:
        rows.insert(0,[{'text':tr('فتح الاستوديو المرئي','Open visual studio'), 'url':studio_url+'/dashboard?project='+raw}])
    if project.telegram_username:
        rows.append([{'text':tr('تجربة البوت في تيليجرام','Try bot in Telegram'), 'url':'https://t.me/'+project.telegram_username}])
    rows += [[button('نشر التعديلات' if published else 'نشر النسخة الأولى', 'Publish changes' if published else 'Publish first version','launchask')],
             [button('الاتصال والإنشاء','Connection & creation','connection'),button('الإعدادات والهوية','Settings & identity','botsettings')]]
    if record and record.enabled and published:
        action = 'stop' if project.status == 'running' else 'resume'
        rows.append([button('إيقاف الاستقبال' if action=='stop' else 'استئناف الاستقبال',
                            'Stop receiving' if action=='stop' else 'Resume receiving',action+'ask')])
    rows.append([{'text':tr('كل بوتاتي','All my bots'), 'callback_data':'projects:0'},
                 {'text':tr('الرئيسية','Home'),'callback_data':'home'}])
    return '\n'.join(body), rows
