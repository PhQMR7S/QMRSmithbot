import re
from copy import deepcopy
from dataclasses import dataclass
from uuid import UUID, uuid4

from qmrsmithbot.templates.catalog import CATALOG, TemplateOptions, get_template

COPY = {
    'ar': {'home': '🏭 مصنع البوتات\nأنشئ مشروعك أو أدر مشاريعك.', 'create': '➕ إنشاء مشروع',
           'projects': '🤖 مشاريعي', 'language': '🌐 اللغة', 'back': '↩ القائمة',
           'choose': 'اختر القالب', 'name': 'اكتب اسم المشروع (حتى 120 حرفًا). /cancel للإلغاء.',
           'welcome': 'اكتب رسالة البداية (حتى 3000 حرف).',
           'rules': 'كل سطر: الكلمة أو الأمر | الرد\nالأوامر بدون /. حتى 100 رد.',
           'confirm': 'إنشاء المسودة', 'summary': 'راجع المسودة قبل الإنشاء',
           'created': '✅ تم إنشاء المسودة. ربط توكن البوت والنشر والتشغيل يحتاج إعداد الخدمة.',
           'empty': 'ما عندك مشاريع بعد.', 'invalid': 'الإدخال غير صحيح. حاول مجددًا أو /cancel.',
           'draft': 'مسودة', 'running': 'يعمل', 'stopped': 'متوقف', 'error': 'خطأ',
           'stop': '⏸ إيقاف', 'resume': '▶ استئناف', 'stopask': 'تأكيد الإيقاف؟ قد تكتمل المهام التي بدأت.',
           'resumeask': 'تأكيد الاستئناف بالإصدار المنشور؟', 'confirmAction': 'تأكيد',
           'saved': '✅ تم الحفظ', 'next': 'التالي', 'prev': 'السابق', 'missing': 'المشروع غير متاح.',
           'admin': '🛠 إدارة المصنع', 'adminInfo': 'حسابك مسجل ضمن مديري المصنع. الإدارة العامة المتقدمة قيد التطوير.',
           'info': 'هذه واجهة إنشاء مسودات وإدارة مشاريع. التشغيل الفعلي يحتاج ربط البوت والاستضافة.'},
    'en': {'home': '🏭 Bot Factory\nCreate or manage your projects.', 'create': '➕ Create project',
           'projects': '🤖 My projects', 'language': '🌐 Language', 'back': '↩ Menu',
           'choose': 'Choose a template', 'name': 'Send a project name (up to 120 characters). /cancel to cancel.',
           'welcome': 'Send the welcome message (up to 3000 characters).',
           'rules': 'One line: keyword or command | reply\nCommands omit /. Up to 100 replies.',
           'confirm': 'Create draft', 'summary': 'Review before creating',
           'created': '✅ Draft created. Bot credentials, publishing and runtime setup are still required.',
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
    def __init__(self, store, *, telegram_id: int, admin: bool = False):
        self.store = store
        self.telegram_id = telegram_id
        self.admin = admin
        self.lang = 'ar'

    def text(self, key):
        return COPY[self.lang][key]

    def button(self, key, data):
        return {'text': self.text(key), 'callback_data': data}

    def response(self, text, rows=None):
        return {'text': text, 'reply_markup': {'inline_keyboard': rows or [[self.button('back', 'home')]]}}

    async def home(self):
        await self.store.save_state(MenuState('idle', {}))
        rows = [[self.button('create', 'create'), self.button('projects', 'projects:0')],
                [self.button('language', 'language')]]
        if self.admin:
            rows.append([self.button('admin', 'admin')])
        return self.response(self.text('home'), rows)

    async def handle(self, *, text=None, callback=None):
        self.lang = await self.store.language()
        if text and re.search(r'\b[0-9]{5,16}:[A-Za-z0-9_-]{20,}\b', text):
            return self.response('لا ترسل التوكن هنا؛ الربط غير مفعّل بعد.' if self.lang == 'ar'
                                 else 'Do not send tokens here; bot linking is not enabled yet.')
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
        if callback == 'create':
            await self.store.save_state(MenuState('idle', {}))
            return self.response(self.text('choose'), [[{'text': t.title_ar if self.lang == 'ar' else t.title_en,
                                   'callback_data': 'template:' + t.id}] for t in CATALOG]
                                 + [[self.button('back', 'home')]])
        if callback and callback.startswith('template:'):
            try:
                template = get_template(callback[9:])
            except KeyError:
                return self.response(self.text('invalid'))
            await self.store.save_state(MenuState('name', {'template': template.id}))
            return self.response(self.text('name'))
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
                    await self.store.save_state(MenuState('action', {
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
            await self.store.save_state(MenuState('idle', {}))
            return self.response(self.text('saved'))
        if callback and callback.startswith('confirm:'):
            if state.step != 'confirm' or callback[8:] != state.data.get('nonce'):
                return self.response(self.text('invalid'))
            options = TemplateOptions.model_validate(state.data['options'])
            template = get_template(state.data['template'])
            definition = template.build(options).model_dump(mode='json')
            await self.store.create(state.data['name'], definition)
            await self.store.save_state(MenuState('idle', {}))
            return self.response(self.text('created'))
        if callback or not text:
            return self.response(self.text('invalid'))
        data = deepcopy(state.data)
        if state.step == 'name' and 0 < len(text.strip()) <= 120:
            data['name'] = text.strip()
            await self.store.save_state(MenuState('welcome', data))
            return self.response(self.text('welcome'))
        if state.step == 'welcome' and 0 < len(text.strip()) <= 3000:
            data['options'] = {'language_code': self.lang, 'welcome': text}
            if data['template'] != 'welcome':
                await self.store.save_state(MenuState('rules', data))
                return self.response(self.text('rules'))
            return await self.review(data)
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

    async def review(self, data):
        data['nonce'] = uuid4().hex
        await self.store.save_state(MenuState('confirm', data))
        count = len(data['options'].get('rules', []))
        return self.response(f'{self.text("summary")}\n{data["name"]}\n{data["template"]}\n'
                             f'{data["options"]["welcome"][:1000]}\n{count}',
                             [[self.button('confirm', 'confirm:' + data['nonce'])], [self.button('back', 'home')]])
