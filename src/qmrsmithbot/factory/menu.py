import re
from copy import deepcopy
from dataclasses import dataclass
from uuid import UUID, uuid4

from qmrsmithbot.factory.presentation import styled_response
from qmrsmithbot.templates.catalog import CATALOG, TemplateOptions, get_template

COPY = {
    'ar': {'home': '✦ QMRSmithbot | مصنع البوتات\n\nمساحة واحدة لبناء بوتك وإدارته.\nاختر قالبًا، خصّص المحتوى، ثم انشره من لوحته.\n\nمن وين تحب تبدأ؟', 'create': '✚ إنشاء بوت',
           'projects': '🤖 بوتاتي', 'language': '🌐 اللغة', 'back': '↩ القائمة',
           'choose': 'اختر القالب', 'name': 'اكتب اسم المشروع (حتى 120 حرفًا). /cancel للإلغاء.',
           'welcome': 'اكتب رسالة البداية (حتى 3000 حرف).',
           'rules': 'كل سطر: الكلمة أو الأمر | الرد\nالأوامر بدون /. حتى 100 رد.',
           'confirm': 'إنشاء المسودة', 'summary': 'راجع المسودة قبل الإنشاء',
           'created': '✅ مشروعك جاهز. افتح لوحة البوت لربط التوكن ومعاينة المحتوى ونشره.',
           'empty': 'ما عندك مشاريع بعد.', 'invalid': 'الإدخال غير صحيح. حاول مجددًا أو /cancel.',
           'draft': 'مسودة', 'running': 'يعمل', 'stopped': 'متوقف', 'error': 'خطأ',
           'stop': '⏸ إيقاف', 'resume': '▶ استئناف', 'stopask': 'تأكيد الإيقاف؟ قد تكتمل المهام التي بدأت.',
           'resumeask': 'تأكيد الاستئناف بالإصدار المنشور؟', 'confirmAction': 'تأكيد',
           'saved': '✅ تم الحفظ', 'next': 'التالي', 'prev': 'السابق', 'missing': 'المشروع غير متاح.',
           'admin': '🛠 إدارة المصنع', 'adminInfo': 'حسابك مسجل ضمن مديري المصنع. الإدارة العامة المتقدمة قيد التطوير.',
           'info': 'هذه واجهة إنشاء مسودات وإدارة مشاريع. التشغيل الفعلي يحتاج ربط البوت والاستضافة.'},
    'en': {'home': '✦ QMRSmithbot | Bot Factory\n\nYour space to build and manage bots.\nChoose a template, make it yours, and publish from its panel.\n\nWhere would you like to start?', 'create': '➕ Create project',
           'projects': '🤖 My projects', 'language': '🌐 Language', 'back': '↩ Menu',
           'choose': 'Choose a template', 'name': 'Send a project name (up to 120 characters). /cancel to cancel.',
           'welcome': 'Send the welcome message (up to 3000 characters).',
           'rules': 'One line: keyword or command | reply\nCommands omit /. Up to 100 replies.',
           'confirm': 'Create draft', 'summary': 'Review before creating',
           'created': '✅ Project ready. Open its panel to connect, preview and publish.',
           'empty': 'No projects yet.', 'invalid': 'Invalid input. Try again or /cancel.',
           'draft': 'Draft', 'running': 'Running', 'stopped': 'Stopped', 'error': 'Error',
           'stop': '⏸ Stop', 'resume': '▶ Resume', 'stopask': 'Confirm stop? In-flight tasks may finish.',
           'resumeask': 'Confirm resume using the published workflow?', 'confirmAction': 'Confirm',
           'saved': '✅ Saved', 'next': 'Next', 'prev': 'Previous', 'missing': 'Project is unavailable.',
           'admin': '🛠 Factory admin', 'adminInfo': 'Your account is configured as a factory administrator. Advanced platform management is under development.',
           'info': 'This interface creates drafts and manages projects. Live delivery requires bot and hosting setup.'},
}


@dataclass
class MenuState:
    step: str
    data: dict


class FactoryMenu:
    """Transport-independent menu/wizard. Store methods are scoped by authenticated identity."""
    def __init__(self, store, *, telegram_id: int, admin: bool = False, management=None):
        self.management = management
        self.store = store
        self.telegram_id = telegram_id
        self.admin = admin
        self.lang = 'ar'

    def text(self, key):
        return COPY[self.lang][key]

    def button(self, key, data):
        return {'text': self.text(key), 'callback_data': data}

    def response(self, text, rows=None):
        return styled_response(text, rows or [[self.button('back', 'home')]])

    async def save_state(self, state):
        previous = await self.store.state()
        state.data.setdefault('_ui', previous.data.get('_ui', {}))
        await self.store.save_state(state)

    async def home(self):
        await self.save_state(MenuState('idle', {}))
        rows = [[self.button('create', 'create'), self.button('projects', 'projects:0')],
                [self.button('language', 'language')]]
        if self.management is not None:
            rows.append([{'text': '📊 إحصائياتي' if self.lang == 'ar' else '📊 Statistics', 'callback_data': 'stats'},
                         {'text': '🧭 المساعدة' if self.lang == 'ar' else '🧭 Help', 'callback_data': 'help'}])
        rows.append([{'text': '🎛 تخصيص العرض' if self.lang == 'ar' else '🎛 Appearance',
                      'callback_data': 'appearance'}])
        if self.admin:
            rows.append([self.button('admin', 'admin')])
        return self.response(self.text('home'), rows)

    async def handle(self, *, text=None, callback=None):
        self.lang = await self.store.language()
        from qmrsmithbot.factory.experience import experience
        response = await experience(self, text=text, callback=callback)
        if response is not None:
            return response
        if self.management is not None:
            response = await self.management.handle(self, text=text, callback=callback)
            if response is not None:
                return response
        if text and re.search(r'\b[0-9]{5,16}:[A-Za-z0-9_-]{20,}\b', text):
            return self.response('افتح لوحة البوت ثم اختر ربط التوكن.' if self.lang == 'ar'
                                 else 'Open your bot panel and choose Connect token.')
        if text and text.split(maxsplit=1) and text.split(maxsplit=1)[0] == '/start':
            text = '/start'
        if text in ('/start', '/cancel') or callback == 'home':
            return await self.home()
        if text == '/help':
            return self.response(self.text('info'))
        if text == '/language' or callback == 'language':
            return self.response('اختر اللغة / Choose language', [[
                {'text': 'العربية', 'callback_data': 'lang:ar'},
                {'text': 'English', 'callback_data': 'lang:en'}]])
        if callback and callback.startswith('lang:'):
            code = callback[5:]
            if code not in COPY:
                return self.response(self.text('invalid'))
            await self.store.set_language(code)
            self.lang = code
            return await self.home()
        if callback == 'admin':
            return self.response(self.text('adminInfo') if self.admin else self.text('missing'))
        state = await self.store.state()
        if callback and callback.startswith('wizard:'):
            step = callback[7:]
            if step not in ('name', 'welcome', 'wizard_key') or 'template' not in state.data:
                return self.response(self.text('invalid'))
            if step != 'name' and 'name' not in state.data:
                return self.response(self.text('invalid'))
            await self.save_state(MenuState(step, dict(state.data)))
            return await self.wizard_prompt(step)
        if callback == 'wizarddefault':
            if state.step != 'welcome':
                return self.response(self.text('invalid'))
            text, callback = ('أهلًا بك 👋' if self.lang == 'ar' else 'Welcome 👋'), None
        if callback == 'wizardadd':
            if state.step != 'wizard_list':
                return self.response(self.text('invalid'))
            await self.save_state(MenuState('wizard_key', dict(state.data)))
            return await self.wizard_prompt('wizard_key')
        if callback == 'wizarddone':
            if state.step != 'wizard_list' or not state.data.get('options', {}).get('rules'):
                return self.response(self.text('invalid'))
            return await self.review(dict(state.data))
        if callback == 'create':
            await self.save_state(MenuState('idle', {}))
            descriptions = ('ترحيب بسيط برسالة بداية جاهزة\nردود نصية لعبارات يرسلها الزائر\nأوامر مثل /help مع ردود مخصصة' if self.lang == 'ar' else 'Welcome: a start message\nText replies: respond to exact phrases\nCommands: custom /help-style replies')
            return self.response('✦ ' + self.text('choose') + '\n\n' + descriptions, [[{'text': t.title_ar if self.lang == 'ar' else t.title_en,
                                   'callback_data': 'template:' + t.id}] for t in CATALOG]
                                 + [[self.button('back', 'home')]])
        if callback and callback.startswith('template:'):
            try:
                template = get_template(callback[9:])
            except KeyError:
                return self.response(self.text('invalid'))
            await self.save_state(MenuState('name', {'template': template.id}))
            return await self.wizard_prompt('name')
        if callback and callback.startswith('projects:'):
            try:
                offset = int(callback[9:])
                if offset < 0 or offset > 2**31 - 1:
                    raise ValueError
            except ValueError:
                return self.response(self.text('invalid'))
            projects = await self.store.projects(offset=offset, limit=9)
            rows = [[{'text': p.name[:60], 'callback_data': f'project:{p.id}'}] for p in projects[:8]]
            pager = []
            if offset:
                pager.append(self.button('prev', f'projects:{max(0, offset - 8)}'))
            if len(projects) > 8:
                pager.append(self.button('next', f'projects:{offset + 8}'))
            if pager:
                rows.append(pager)
            rows.append([self.button('back', 'home')])
            return self.response(self.text('projects') if projects else self.text('empty'), rows)
        if callback and ':' in callback:
            action, raw = callback.split(':', 1)
            if action in ('project', 'stopask', 'resumeask'):
                try:
                    project_id = UUID(raw)
                except ValueError:
                    return self.response(self.text('invalid'))
                project = await self.store.project(project_id)
                if project is None:
                    return self.response(self.text('missing'))
                if action in ('stopask', 'resumeask'):
                    nonce = uuid4().hex
                    await self.save_state(MenuState('action', {
                        'nonce': nonce, 'project_id': raw, 'running': action == 'resumeask'}))
                    return self.response(self.text(action), [[self.button('confirmAction',
                            'apply:' + nonce)], [self.button('back', 'home')]])
                rows = []
                if project.status in ('running', 'stopped'):
                    op = 'stop' if project.status == 'running' else 'resume'
                    rows.append([self.button(op, op + 'ask:' + raw)])
                rows.append([self.button('back', 'home')])
                return self.response(f'{project.name}\n{self.text(project.status)}\n'
                                     f'v{project.active_version or "—"}', rows)
        state = await self.store.state()
        if callback and callback.startswith('apply:'):
            if state.step != 'action' or callback[6:] != state.data.get('nonce'):
                return self.response(self.text('invalid'))
            await self.store.set_running(UUID(state.data['project_id']), state.data['running'])
            await self.save_state(MenuState('idle', {}))
            return self.response(self.text('saved'))
        if callback and callback.startswith('confirm:'):
            if state.step != 'confirm' or callback[8:] != state.data.get('nonce'):
                return self.response(self.text('invalid'))
            options = TemplateOptions.model_validate(state.data['options'])
            template = get_template(state.data['template'])
            definition = template.build(options).model_dump(mode='json')
            project = await self.store.create(state.data['name'], definition)
            await self.save_state(MenuState('idle', {}))
            rows = None
            if project is not None and self.management is not None:
                rows = [[{'text': '🤖 لوحة البوت' if self.lang == 'ar' else '🤖 Bot panel',
                          'callback_data': f'project:{project.id}'}], [self.button('back', 'home')]]
            return self.response(self.text('created'), rows)
        if callback or not text:
            return self.response(self.text('invalid'))
        data = deepcopy(state.data)
        if state.step == 'name' and 0 < len(text.strip()) <= 120:
            data['name'] = text.strip()
            if data.get('options', {}).get('welcome'):
                return await self.review(data)
            await self.save_state(MenuState('welcome', data))
            return await self.wizard_prompt('welcome')
        if state.step == 'welcome' and 0 < len(text.strip()) <= 3000:
            data['options'] = {**data.get('options', {}), 'language_code': self.lang, 'welcome': text}
            if data['template'] != 'welcome':
                if data['options'].get('rules'):
                    return await self.review(data)
                data['options']['rules'] = []
                await self.save_state(MenuState('wizard_key', data))
                return await self.wizard_prompt('wizard_key')
            return await self.review(data)
        if state.step == 'wizard_key':
            key = text.strip().lstrip('/') if data['template'] == 'command-menu' else text.strip()
            if not key or len(key) > 100 or key.startswith('/') or len(data['options'].get('rules', [])) >= 100:
                return self.response(self.text('invalid'))
            if data['template'] == 'command-menu' and (key == 'start' or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', key)):
                return self.response(self.text('invalid'))
            if key in {r['trigger'] for r in data['options'].get('rules', [])}:
                return self.response(self.text('invalid'))
            data['pending_key'] = key
            await self.save_state(MenuState('wizard_reply', data))
            return await self.wizard_prompt('wizard_reply')
        if state.step == 'wizard_reply' and 0 < len(text.strip()) <= 3000:
            data['options']['rules'].append({'trigger': data.pop('pending_key'), 'response': text})
            await self.save_state(MenuState('wizard_list', data))
            label = '✅ أضفنا الرد. تكدر تضيف غيره أو تكمل للمراجعة.' if self.lang == 'ar' else '✅ Reply added. Add another or continue to review.'
            return self.response(label, [[{'text': '✚ إضافة آخر' if self.lang == 'ar' else '✚ Add another', 'callback_data': 'wizardadd'},
                {'text': 'متابعة ←' if self.lang == 'ar' else 'Continue →', 'callback_data': 'wizarddone'}], [self.button('back', 'home')]])
        if state.step == 'rules':
            rules = []
            for line in text.splitlines():
                if not line.strip():
                    continue
                key, separator, value = line.partition('|')
                if not separator or not key.strip() or not value.strip():
                    return self.response(self.text('invalid'))
                rules.append({'trigger': key.strip(), 'response': value.strip()})
            data['options']['rules'] = rules
            try:
                get_template(data['template']).build(TemplateOptions.model_validate(data['options']))
            except ValueError:
                return self.response(self.text('invalid'))
            return await self.review(data)
        return self.response(self.text('invalid'))

    async def wizard_prompt(self, step):
        ar = self.lang == 'ar'
        prompts = {
            'name': ('① هوية البوت\n\nشنو تحب تسمّي مشروعك؟ اكتب الاسم، حتى 120 حرفًا.', '① Bot identity\n\nWhat would you like to call your project? Send up to 120 characters.'),
            'welcome': ('② أول انطباع\n\nشنو يظهر للزائر عند /start؟ أرسل رسالة البداية، أو اختر الرسالة الجاهزة.', '② First impression\n\nWhat should visitors see on /start? Send your welcome or use the default.'),
            'wizard_key': ('③ أضف ردّك\n\nأرسل الكلمة أو العبارة، أو اسم الأمر بالإنجليزية للقالب الخاص بالأوامر. بعدها نطلب نص الرد.', '③ Add your reply\n\nSend an exact phrase, or an English command name for the command template. Next we ask for its response.'),
            'wizard_reply': ('③ نص الرد\n\nهسه أرسل النص اللي يرد به البوت، حتى 3000 حرف.', '③ Response text\n\nNow send what the bot should reply, up to 3000 characters.')}
        rows = []
        if step == 'welcome':
            rows.append([{'text': 'استخدام رسالة جاهزة' if ar else 'Use default welcome', 'callback_data': 'wizarddefault'}])
        previous = {'name': 'create', 'welcome': 'wizard:name', 'wizard_key': 'wizard:welcome', 'wizard_reply': 'wizard:wizard_key'}[step]
        rows.append([{'text': '↩ الخطوة السابقة' if ar else '↩ Previous step', 'callback_data': previous}, self.button('back', 'home')])
        return self.response(prompts[step][0 if ar else 1], rows)

    async def review(self, data):
        data['nonce'] = uuid4().hex
        await self.save_state(MenuState('confirm', data))
        count = len(data['options'].get('rules', []))
        return self.response(f'{self.text("summary")}\n{data["name"]}\n{data["template"]}\n'
                             f'{data["options"]["welcome"][:1000]}\n{count}',
                             [[self.button('confirm', 'confirm:' + data['nonce'])],
                              [{'text': '✏️ الاسم' if self.lang == 'ar' else '✏️ Name', 'callback_data': 'wizard:name'},
                               {'text': '💬 البداية' if self.lang == 'ar' else '💬 Welcome', 'callback_data': 'wizard:welcome'}],
                              [self.button('back', 'home')]])
