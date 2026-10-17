"""Version-aware, individual reply editing with tenant authorization on every operation."""
import re
from copy import deepcopy
from uuid import UUID, uuid4

from qmrsmithbot.auth.models import Permission
from qmrsmithbot.factory.menu import MenuState
from qmrsmithbot.telegram.inline_runtime import InlineBotError, compile_text_program


class ReplyEditor:
    def __init__(self, management, menu):
        self.manager, self.menu = management, menu

    def tr(self, ar, en):
        return ar if self.menu.lang == 'ar' else en

    def button(self, ar, en, data):
        return {'text': self.tr(ar, en), 'callback_data': data}

    def back(self, project_id):
        return [self.button('↩ محرر المحتوى', '↩ Content editor', f'content:{project_id}')]

    @staticmethod
    def entries(definition):
        result = []
        nodes = {n['id']: n for n in definition['nodes']}
        for node in definition['nodes']:
            if node['type'] not in ('trigger.command', 'trigger.message'):
                continue
            key = 'command' if node['type'] == 'trigger.command' else 'text'
            if key == 'command' and node['config'][key] == 'start':
                continue
            edge = next(e for e in definition['edges'] if e['source'] == node['id'])
            result.append((node, nodes[edge['target']]))
        return result

    async def persist(self, project_id, definition, expected):
        await self.manager.project(project_id, Permission.PROJECT_WRITE, lock=True)
        latest = await self.manager.latest(project_id)
        if latest.version != expected:
            raise InlineBotError('stale')
        compile_text_program(definition)
        await self.manager.store.projects_service.save_version(project_id=project_id,
            tenant_id=self.manager.store.tenant_id, definition=definition)
        await self.manager.store.audit('factory.reply.saved', project_id,
            self.manager.store.user.id, self.manager.store.tenant_id)

    async def listing(self, project_id, offset=0):
        project = await self.manager.project(project_id)
        version = await self.manager.latest(project_id)
        program = compile_text_program(version.definition)
        items = self.entries(version.definition)
        rows = [[self.button('💬 رسالة البداية', '💬 Welcome message', f'welcome:{project_id}'),
                 self.button('👁 معاينة', '👁 Preview', f'preview:{project_id}')]]
        for i, (trigger, _) in enumerate(items[offset:offset+6], offset):
            command = trigger['type'] == 'trigger.command'
            label = ('/' if command else '💬 ') + trigger['config']['command' if command else 'text']
            rows.append([{'text': label[:60], 'callback_data': f'ri:{project_id}:{version.version}:{i}'}])
        pager = []
        if offset:
            pager.append(self.button('السابق', 'Previous', f'rl:{project_id}:{max(0,offset-6)}'))
        if offset+6 < len(items):
            pager.append(self.button('التالي', 'Next', f'rl:{project_id}:{offset+6}'))
        if pager:
            rows.append(pager)
        rows += [[self.button('✚ رد نصّي', '✚ Text reply', f'ra:{project_id}:m'),
                  self.button('✚ أمر', '✚ Command', f'ra:{project_id}:c')],
                 [self.button('🚀 نشر التعديلات', '🚀 Publish changes', f'launchask:{project_id}')],
                 [self.button('↩ لوحة البوت', '↩ Bot panel', f'project:{project_id}')]]
        text = self.tr('📝 استوديو المحتوى', '📝 Content studio') + '\n' + project.name
        text += self.tr(f'\n\nرسالة بداية · {len(program.messages)} رد · {len(program.commands)-1} أمر',
                        f'\n\nWelcome · {len(program.messages)} replies · {len(program.commands)-1} commands')
        text += self.tr('\n\nاختَر عنصرًا لمعاينته وتعديله أو حذفه. تقدر تجمع الردود والأوامر بنفس البوت.\nتُحفظ التغييرات كمسودات حتى تنشرها.',
                        '\n\nChoose an item to preview, edit or delete. Replies and commands can coexist.\nChanges remain drafts until published.')
        await self.menu.save_state(MenuState('idle', {}))
        return self.menu.response(text, rows)

    async def handle(self, *, text=None, callback=None):
        state = await self.manager.store.state()
        parts = callback.split(':') if callback else []
        actions = ('content', 'rl', 'ri', 'ra', 're', 'rd')
        if parts and parts[0] in actions:
            action = parts[0]
            if len(parts) != {'content': 2, 'rl': 3, 'ra': 3, 'ri': 4, 're': 4, 'rd': 4}[action]:
                raise ValueError()
            project_id = UUID(parts[1])
            await self.manager.project(project_id)
            version = await self.manager.latest(project_id)
            compile_text_program(version.definition)
            if action in ('content', 'rl'):
                offset = int(parts[2]) if action == 'rl' else 0
                if not 0 <= offset <= 100:
                    raise ValueError()
                return await self.listing(project_id, offset)
            await self.manager.store.permission(Permission.PROJECT_WRITE)
            if action == 'ra':
                kind = parts[2]
                if kind not in ('m', 'c') or len(self.entries(version.definition)) >= 100:
                    raise ValueError()
                await self.menu.save_state(MenuState('reply_key', {'project_id': str(project_id),
                    'kind': kind, 'version': version.version}))
                prompt = self.tr('✚ أمر جديد\n\nاكتب اسم الأمر، مثل help. الحروف الإنجليزية الصغيرة والأرقام و _ فقط، حتى 32 حرفًا.',
                    '✚ New command\n\nSend its name, such as help. Lowercase English letters, digits and _ only, up to 32 characters.') if kind == 'c' else self.tr('✚ رد جديد\n\nشنو الكلمة أو العبارة اللي تريد البوت يرد عليها؟ اكتبها برسالة واحدة، حتى 100 حرف.',
                    '✚ New reply\n\nWhich exact word or phrase should trigger it? Send up to 100 characters.')
                return self.menu.response(prompt, [self.back(project_id)])
            expected, index = int(parts[2]), int(parts[3])
            if expected != version.version:
                raise InlineBotError('stale')
            items = self.entries(version.definition)
            if not 0 <= index < len(items):
                raise ValueError()
            trigger, reply = items[index]
            key = 'command' if trigger['type'] == 'trigger.command' else 'text'
            label = ('/' if key == 'command' else '') + trigger['config'][key]
            if action == 'ri':
                return self.menu.response(self.tr('📝 تفاصيل الرد\n\n', '📝 Reply details\n\n')+label+'\n\n'+reply['config']['text'],
                    [[self.button('✏️ تعديل النص', '✏️ Edit response', f're:{project_id}:{expected}:{index}'),
                      self.button('🗑 حذف', '🗑 Delete', f'rd:{project_id}:{expected}:{index}')], self.back(project_id)])
            data = {'project_id': str(project_id), 'version': expected, 'index': index}
            if action == 're':
                await self.menu.save_state(MenuState('reply_body', data))
                return self.menu.response(self.tr('✏️ تعديل الرد\n\nأرسل النص البديل، حتى 3000 حرف. الكلمة أو الأمر يبقى كما هو.',
                    '✏️ Edit response\n\nSend the replacement text, up to 3000 characters. Its trigger stays unchanged.'), [self.back(project_id)])
            nonce = uuid4().hex
            await self.menu.save_state(MenuState('reply_delete', {**data, 'nonce': nonce}))
            return self.menu.response(self.tr('حذف هذا الرد من المسودة؟\n', 'Delete this reply from the draft?\n')+label,
                [[self.button('🗑 تأكيد الحذف', '🗑 Confirm deletion', 'ruledeleteok:'+nonce)], self.back(project_id)])
        if callback and callback.startswith('ruledeleteok:'):
            if state.step != 'reply_delete' or callback[13:] != state.data.get('nonce'):
                return self.menu.response(self.menu.text('invalid'))
            data = state.data
            project_id = UUID(data['project_id'])
            await self.manager.project(project_id, Permission.PROJECT_WRITE, lock=True)
            version = await self.manager.latest(project_id)
            if version.version != data['version']:
                raise InlineBotError('stale')
            definition = deepcopy(version.definition)
            trigger, reply = self.entries(definition)[data['index']]
            definition['edges'] = [e for e in definition['edges'] if e['source'] != trigger['id']]
            used = any(e['target'] == reply['id'] for e in definition['edges'])
            remove = {trigger['id']} | (set() if used else {reply['id']})
            definition['nodes'] = [n for n in definition['nodes'] if n['id'] not in remove]
            await self.persist(project_id, definition, data['version'])
            return await self.listing(project_id)
        if not text or text in ('/start', '/cancel', '/help', '/language') or state.step not in ('reply_key', 'reply_body'):
            return None
        if re.search(r'\b[0-9]{5,16}:[A-Za-z0-9_-]{20,}\b', text):
            raise InlineBotError('token')
        data = dict(state.data)
        project_id = UUID(data['project_id'])
        await self.manager.project(project_id, Permission.PROJECT_WRITE, lock=True)
        version = await self.manager.latest(project_id)
        if version.version != data['version']:
            raise InlineBotError('stale')
        if state.step == 'reply_key':
            key = text.strip().lstrip('/') if data['kind'] == 'c' else text.strip()
            if not key or len(key) > 100 or key.startswith('/') or (data['kind'] == 'c'
                    and (key == 'start' or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', key))):
                raise ValueError()
            program = compile_text_program(version.definition)
            if key in (program.commands if data['kind'] == 'c' else program.messages):
                raise InlineBotError('duplicate')
            data['key'] = key
            await self.menu.save_state(MenuState('reply_body', data))
            return self.menu.response(self.tr('💬 نص الرد\n\nأرسل الرد الذي سيظهر للزائر، حتى 3000 حرف.',
                '💬 Response text\n\nSend what visitors should receive, up to 3000 characters.'), [self.back(project_id)])
        if not 0 < len(text.strip()) <= 3000:
            raise ValueError()
        definition = deepcopy(version.definition)
        if 'index' in data:
            trigger, reply = self.entries(definition)[data['index']]
            # Split shared actions rather than editing another trigger's response.
            target = 'reply_' + uuid4().hex
            definition['nodes'].append({'id': target, 'type': 'action.message', 'config': {'text': text}})
            for edge in definition['edges']:
                if edge['source'] == trigger['id']:
                    edge['target'] = target
            if not any(e['target'] == reply['id'] for e in definition['edges']):
                definition['nodes'] = [n for n in definition['nodes'] if n['id'] != reply['id']]
        else:
            node_id = 'rule_' + uuid4().hex
            key = 'command' if data['kind'] == 'c' else 'text'
            definition['nodes'] += [{'id': node_id, 'type': 'trigger.command' if key == 'command' else 'trigger.message', 'config': {key: data['key']}},
                {'id': node_id+'_reply', 'type': 'action.message', 'config': {'text': text}}]
            definition['edges'].append({'source': node_id, 'target': node_id+'_reply'})
        await self.persist(project_id, definition, data['version'])
        return await self.listing(project_id)
