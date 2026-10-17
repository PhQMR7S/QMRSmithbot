"""Tenant-scoped bot management; raw credentials never enter conversation state."""
import re
from copy import deepcopy
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from qmrsmithbot.auth.models import Permission
from qmrsmithbot.config import settings
from qmrsmithbot.db.factory_models import TelegramInlineBotRecord
from qmrsmithbot.db.models import BotCredentialRecord, BotProjectRecord, WorkflowVersionRecord
from qmrsmithbot.factory.menu import MenuState
from qmrsmithbot.telegram.inline_runtime import (
    InlineBotError,
    child_webhook_secret,
    compile_text_program,
)
from qmrsmithbot.telegram.provisioning import (
    _credential_cipher,
    decrypt_bot_token,
    hash_webhook_secret,
)
from qmrsmithbot.templates.catalog import TemplateOptions, get_template


def make_bot(token):
    return Bot(token, session=AiohttpSession(timeout=8))


class BotManagement:
    def __init__(self, store):
        self.store, self.session = store, store.session

    async def project(self, project_id, permission=Permission.PROJECT_READ, lock=False):
        await self.store.permission(permission)
        query = select(BotProjectRecord).where(BotProjectRecord.id == project_id,
                                              BotProjectRecord.tenant_id == self.store.tenant_id)
        if lock:
            query = query.with_for_update()
        project = await self.session.scalar(query)
        if project is None:
            raise InlineBotError('missing')
        return project

    async def latest(self, project_id):
        version = await self.session.scalar(select(WorkflowVersionRecord).where(
            WorkflowVersionRecord.project_id == project_id).order_by(WorkflowVersionRecord.version.desc()).limit(1))
        if version is None:
            raise InlineBotError('missing')
        return version

    async def bind(self, project_id, token):
        await self.project(project_id, Permission.PROJECT_WRITE)
        if not settings.telegram_inline_runtime_enabled:
            raise InlineBotError('unavailable')
        token = token.strip()
        if not re.fullmatch(r'[0-9]{5,16}:[A-Za-z0-9_-]{30,100}', token):
            raise InlineBotError('token')
        if token.split(':')[0] == settings.telegram_factory_bot_token.get_secret_value().split(':')[0]:
            raise InlineBotError('factory')
        bot = make_bot(token)
        try:
            me = await bot.get_me()
        except (TelegramAPIError, OSError, TimeoutError, RuntimeError):
            raise InlineBotError('token') from None
        finally:
            await bot.session.close()
        if not me.is_bot or me.id != int(token.split(':')[0]):
            raise InlineBotError('token')
        await self.session.execute(select(func.pg_advisory_xact_lock(64532, me.id % (2**31-1))))
        try:
            async with self.session.begin_nested():
                project = await self.project(project_id, Permission.PROJECT_WRITE, lock=True)
                if project.telegram_bot_id is not None and project.telegram_bot_id != me.id:
                    raise InlineBotError('different')
                other = await self.session.scalar(select(BotProjectRecord.id).where(
                    BotProjectRecord.telegram_bot_id == me.id, BotProjectRecord.id != project_id))
                if other is not None:
                    raise InlineBotError('assigned')
                credential = await self.session.get(BotCredentialRecord, project_id)
                if credential is None:
                    credential = BotCredentialRecord(project_id=project_id, token_version=0)
                    self.session.add(credential)
                credential.token_ciphertext = _credential_cipher().encrypt(token.encode()).decode()
                credential.token_last4 = token[-4:]
                credential.token_version += 1
                credential.webhook_secret_hash = hash_webhook_secret(child_webhook_secret(project_id))
                project.telegram_bot_id, project.telegram_username = me.id, me.username
                await self.session.flush()
                await self.store.audit('factory.bot.bound', project_id, self.store.user.id, self.store.tenant_id)
        except IntegrityError:
            raise InlineBotError('assigned') from None
        return me.username

    async def launch(self, project_id):
        if not settings.telegram_inline_runtime_enabled:
            raise InlineBotError('unavailable')
        base = settings.telegram_ingress_base_url.rstrip('/')
        parsed = urlsplit(base)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.query or parsed.fragment or parsed.path or parsed.username or parsed.password:
            raise InlineBotError('unavailable')
        async with self.session.begin_nested():
            project = await self.project(project_id, Permission.PROJECT_PUBLISH, lock=True)
            version = await self.latest(project_id)
            compile_text_program(version.definition)
            credential = await self.session.get(BotCredentialRecord, project_id)
            if credential is None or project.telegram_bot_id is None:
                raise InlineBotError('unbound')
            await self.store.projects_service.publish(project_id=project_id, tenant_id=self.store.tenant_id,
                actor_user_id=self.store.user.id, version=version.version)
            url = base + '/bots/' + str(project_id)
            credential.webhook_secret_hash = hash_webhook_secret(child_webhook_secret(project_id))
            bot = make_bot(decrypt_bot_token(credential.token_ciphertext))
            try:
                ok = await bot.set_webhook(url=url, secret_token=child_webhook_secret(project_id),
                    allowed_updates=['message'], max_connections=1, drop_pending_updates=False)
                info = await bot.get_webhook_info()
                if not ok or info.url != url:
                    raise RuntimeError()
            except (TelegramAPIError, OSError, TimeoutError, RuntimeError):
                raise InlineBotError('launch') from None
            finally:
                await bot.session.close()
            record = await self.session.get(TelegramInlineBotRecord, project_id)
            if record is None:
                record = TelegramInlineBotRecord(project_id=project_id)
                self.session.add(record)
            record.enabled, record.webhook_url = True, url
            record.verified_at = datetime.now(UTC)
            await self.session.flush()
            await self.store.audit('factory.bot.activated', project_id, self.store.user.id, self.store.tenant_id)

    async def save_content(self, project_id, *, welcome=None, rules=None, mode=None):
        await self.project(project_id, Permission.PROJECT_WRITE, lock=True)
        version = await self.latest(project_id)
        program = compile_text_program(version.definition)
        if welcome is not None:
            definition = deepcopy(version.definition)
            starts = {n['id'] for n in definition['nodes'] if n['type'] == 'trigger.command'
                      and n['config'].get('command') == 'start'}
            targets = {e['target'] for e in definition['edges'] if e['source'] in starts}
            for node in definition['nodes']:
                if node['id'] in targets:
                    node['config']['text'] = welcome
        else:
            definition = get_template(mode).build(TemplateOptions(
                welcome=program.commands['start'], rules=rules)).model_dump(mode='json')
        compile_text_program(definition)
        await self.store.projects_service.save_version(project_id=project_id,
            tenant_id=self.store.tenant_id, definition=definition)
        await self.store.audit('factory.bot.content_saved', project_id, self.store.user.id, self.store.tenant_id)

    async def handle(self, menu, *, text=None, callback=None):
        def tr(ar, en):
            return ar if menu.lang == 'ar' else en
        def button(ar, en, data):
            return {'text': tr(ar, en), 'callback_data': data}
        def back(project_id):
            return [button('↩ لوحة البوت', '↩ Bot panel', 'project:' + str(project_id))]
        state = await self.store.state()
        try:
            if callback in ('stats', 'admin'):
                if callback == 'admin' and not menu.admin:
                    return menu.response(menu.text('missing'))
                await self.store.permission(Permission.PROJECT_READ)
                query = select(BotProjectRecord.status, func.count()).group_by(BotProjectRecord.status)
                if callback != 'admin':
                    query = query.where(BotProjectRecord.tenant_id == self.store.tenant_id)
                counts = dict((await self.session.execute(query)).all())
                title = tr('📊 إحصائيات المصنع' if callback == 'admin' else '📊 إحصائياتي',
                           '📊 Factory overview' if callback == 'admin' else '📊 My statistics')
                body = '\n'.join(f'{menu.text(key)}: {counts.get(key, 0)}'
                                 for key in ('running', 'stopped', 'draft', 'error'))
                return menu.response(title + '\n\n' + body)
            if callback == 'help' or text == '/help':
                return menu.response(tr('🧭 خطوات إنشاء بوتك\n\n1. اختر قالبًا وأدخل المحتوى.\n2. افتح لوحة المشروع واربط توكن البوت من @BotFather.\n3. عاين المحتوى ثم اضغط «نشر وتشغيل».\n\nيمكنك تعديل الترحيب والردود وإيقاف البوت من لوحته. التوكن يُشفّر ولا يظهر في اللوحة.',
                    '🧭 Create your bot\n\n1. Choose a template and add content.\n2. Open its panel and connect the bot token from @BotFather.\n3. Preview, then Publish & run.\n\nEdit content or stop your bot from its panel. Tokens are encrypted and never displayed.'))
            if callback and ':' in callback:
                action, raw = callback.split(':', 1)
                if action in ('project', 'bind', 'preview', 'rename', 'welcome', 'rules', 'rulesmsg', 'rulescmd', 'launchask'):
                    project_id = UUID(raw)
                    project = await self.project(project_id)
                    if action == 'project':
                        await self.store.save_state(MenuState('idle', {}))
                        version = await self.latest(project_id)
                        record = await self.session.get(TelegramInlineBotRecord, project_id)
                        connected = '@' + project.telegram_username if project.telegram_username else tr('غير مربوط', 'Not connected')
                        status = menu.text(project.status)
                        rows = [[button('🔗 ربط / تحديث التوكن', '🔗 Connect / update token', 'bind:' + raw),
                                 button('👁 معاينة', '👁 Preview', 'preview:' + raw)],
                                [button('💬 رسالة البداية', '💬 Welcome message', 'welcome:' + raw),
                                 button('📝 الردود والأوامر', '📝 Replies & commands', 'rules:' + raw)],
                                [button('✏️ الاسم', '✏️ Rename', 'rename:' + raw),
                                 button('🚀 نشر وتشغيل', '🚀 Publish & run', 'launchask:' + raw)]]
                        if record is not None and record.enabled and project.active_version:
                            op = 'stop' if project.status == 'running' else 'resume'
                            rows.append([menu.button(op, op + 'ask:' + raw)])
                        rows.append([menu.button('back', 'home')])
                        return menu.response(f'🤖 {project.name}\n{connected}\n{status}\n'
                            + tr(f'الإصدار المنشور: {project.active_version or "—"}\nآخر مسودة: {version.version}',
                                 f'Published version: {project.active_version or "—"}\nLatest draft: {version.version}'), rows)
                    if action == 'preview':
                        program = compile_text_program((await self.latest(project_id)).definition)
                        return menu.response(tr('👁 معاينة رسالة البداية\n\n', '👁 Welcome preview\n\n')
                            + program.commands['start'] + tr(f'\n\nالردود: {len(program.messages)} | الأوامر: {len(program.commands)-1}',
                                f'\n\nReplies: {len(program.messages)} | Commands: {len(program.commands)-1}'), [back(project_id)])
                    if action == 'rules':
                        return menu.response(tr('اختر نوع القائمة الجديدة. الحفظ يستبدل الردود/الأوامر السابقة ويُبقي رسالة البداية.',
                            'Choose the replacement list type. Saving replaces existing replies/commands and keeps the welcome message.'),
                            [[button('💬 ردود نصية', '💬 Text replies', 'rulesmsg:' + raw),
                              button('⌨️ أوامر', '⌨️ Commands', 'rulescmd:' + raw)], back(project_id)])
                    await self.store.permission(Permission.PROJECT_WRITE)
                    if action == 'launchask':
                        nonce = uuid4().hex
                        await self.store.save_state(MenuState('bot_launch', {'project_id': raw, 'nonce': nonce}))
                        return menu.response(tr('نشر آخر مسودة وتشغيل البوت؟ سيُربط بالمصنع ويُستبدل الـWebhook الحالي إن وجد.',
                            'Publish the latest draft and run this bot? This connects it to the factory and replaces any current webhook.'),
                            [[button('✅ نشر وتشغيل', '✅ Publish & run', 'launchok:' + nonce)], back(project_id)])
                    step = {'bind': 'bot_token', 'rename': 'bot_name', 'welcome': 'bot_welcome',
                            'rulesmsg': 'bot_rules', 'rulescmd': 'bot_rules'}[action]
                    await self.store.save_state(MenuState(step, {'project_id': raw,
                        'mode': 'auto-replies' if action == 'rulesmsg' else 'command-menu'}))
                    prompt = {'bind': tr('🔐 أرسل توكن البوت من @BotFather في رسالة واحدة. يُشفّر عند الحفظ، وسنحاول حذف رسالة التوكن. /cancel للإلغاء. لا تستخدم توكن المصنع.',
                                        '🔐 Send the bot token from @BotFather in one message. It is encrypted on save; we attempt to delete the token message. /cancel to cancel. Do not use the factory token.'),
                              'rename': tr('اكتب الاسم الجديد، حتى 120 حرفًا.', 'Send the new name, up to 120 characters.'),
                              'welcome': tr('اكتب رسالة البداية الجديدة، حتى 3000 حرف. تُحفظ كمسودة لحين النشر.', 'Send the new welcome message, up to 3000 characters. It is saved as a draft until published.'),
                              'rulesmsg': menu.text('rules'), 'rulescmd': menu.text('rules')}[action]
                    return menu.response(prompt, [back(project_id)])
                if action == 'launchok':
                    if state.step != 'bot_launch' or raw != state.data.get('nonce'):
                        return menu.response(menu.text('invalid'))
                    project_id = UUID(state.data['project_id'])
                    await self.launch(project_id)
                    await self.store.save_state(MenuState('idle', {}))
                    return menu.response(tr('✅ نُشر البوت وتم التحقق من ربطه. افتحه وأرسل /start.',
                        '✅ Published and webhook verified. Open your bot and send /start.'), [back(project_id)])
            if text and not text.startswith('/') and state.step in ('bot_token', 'bot_name', 'bot_welcome', 'bot_rules'):
                project_id = UUID(state.data['project_id'])
                if state.step == 'bot_token':
                    username = await self.bind(project_id, text)
                    result = tr('✅ تم ربط البوت بأمان: @', '✅ Bot securely connected: @') + (username or '')
                else:
                    if re.search(r'\b[0-9]{5,16}:[A-Za-z0-9_-]{20,}\b', text):
                        raise InlineBotError('token')
                    if state.step == 'bot_name':
                        await self.project(project_id, Permission.PROJECT_WRITE)
                        await self.store.projects_service.rename(project_id=project_id, tenant_id=self.store.tenant_id,
                            name=text, actor_user_id=self.store.user.id)
                        result = menu.text('saved')
                    elif state.step == 'bot_welcome':
                        if not 0 < len(text.strip()) <= 3000:
                            raise ValueError()
                        await self.save_content(project_id, welcome=text)
                        result = tr('✅ حُفظت مسودة جديدة. اضغط نشر وتشغيل لتطبيقها.', '✅ New draft saved. Publish & run to apply it.')
                    else:
                        rules = []
                        for line in text.splitlines():
                            key, sep, value = line.partition('|')
                            if not sep or not key.strip() or not value.strip():
                                raise ValueError()
                            rules.append({'trigger': key.strip(), 'response': value.strip()})
                        await self.save_content(project_id, rules=rules, mode=state.data['mode'])
                        result = tr('✅ حُفظت الردود كمسودة. انشرها لتطبيق التغييرات.', '✅ Replies saved as a draft. Publish to apply changes.')
                await self.store.save_state(MenuState('idle', {}))
                return menu.response(result, [back(project_id)])
        except ValueError as exc:
            errors = {'token': tr('التوكن غير صالح أو لم يقبله تيليجرام. تأكد منه وحاول مجددًا.', 'Invalid token or Telegram rejected it. Check it and try again.'),
                      'factory': tr('هذا توكن المصنع. استخدم توكن بوت آخر.', 'This is the factory token. Use a different bot.'),
                      'assigned': tr('هذا البوت مربوط بمشروع آخر.', 'This bot is connected to another project.'),
                      'different': tr('المشروع مربوط ببوت آخر. أنشئ مشروعًا جديدًا للبوت الجديد.', 'This project already has a different bot. Create a new project for the new bot.'),
                      'unbound': tr('اربط توكن البوت أولًا.', 'Connect the bot token first.'),
                      'missing': menu.text('missing'),
                      'launch': tr('تعذر تأكيد التشغيل من تيليجرام. أعد المحاولة.', 'Telegram activation could not be verified. Try again.'),
                      'unavailable': tr('خدمة التشغيل قيد التجهيز. حاول لاحقًا.', 'Runtime setup is in progress. Try later.')}
            return menu.response(errors.get(str(exc), tr('تعذر حفظ الإعداد. راجع المحتوى؛ التشغيل الحالي يدعم القوالب النصية فقط.',
                'Could not save this setting. Check the content; this runtime supports plain-text templates only.')))
        return None
