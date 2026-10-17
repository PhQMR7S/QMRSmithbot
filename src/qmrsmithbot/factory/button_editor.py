"""Draft/live hierarchical button editor. There is no application-level item-count quota."""
import re
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import select

from qmrsmithbot.auth.models import Permission
from qmrsmithbot.db.factory_models import FactoryButtonRecord
from qmrsmithbot.factory.menu import MenuState
from qmrsmithbot.telegram.inline_runtime import InlineBotError, compile_text_program


class ButtonEditor:
    def __init__(self, manager, menu):
        self.manager, self.menu, self.session = manager, menu, manager.session

    def tr(self, ar, en):
        return ar if self.menu.lang == 'ar' else en

    def button(self, ar, en, data):
        return {'text': self.tr(ar, en), 'callback_data': data}

    async def project(self, project_id, write=False):
        project = await self.manager.project(project_id,
            Permission.PROJECT_WRITE if write else Permission.PROJECT_READ, lock=write)
        version = await self.manager.latest(project_id)
        if compile_text_program(version.definition).kind != 'buttons':
            raise ValueError('This is not a button bot')
        return project

    async def item(self, item_id, write=False):
        # Resolve the item through its tenant-scoped project, never by a global item lookup.
        from qmrsmithbot.db.models import BotProjectRecord
        item = await self.session.scalar(select(FactoryButtonRecord).join(BotProjectRecord,
            BotProjectRecord.id == FactoryButtonRecord.project_id).where(
            FactoryButtonRecord.id == item_id, BotProjectRecord.tenant_id == self.manager.store.tenant_id,
            FactoryButtonRecord.deleted.is_(False)))
        if item is None:
            raise InlineBotError('missing')
        await self.project(item.project_id, write=write)
        return item

    def back(self, project_id, parent_id=None):
        return [self.button('↩ قائمة الأزرار', '↩ Buttons', 'folder:'+parent_id.hex if parent_id else 'buttons:'+str(project_id))]

    async def listing(self, project_id, parent=None, offset=0):
        project = await self.project(project_id)
        folder = await self.item(parent) if parent else None
        if folder and folder.draft['kind'] != 'section':
            raise ValueError()
        items = (await self.session.scalars(select(FactoryButtonRecord).where(
            FactoryButtonRecord.project_id == project_id, FactoryButtonRecord.parent_id == parent,
            FactoryButtonRecord.deleted.is_(False)).order_by(FactoryButtonRecord.created_at, FactoryButtonRecord.id).offset(offset).limit(7))).all()
        rows = []
        for item in items[:6]:
            prefix = {'section': '🗂', 'text': '💬', 'url': '🔗', 'file': '📎'}[item.draft['kind']]
            rows.append([{'text': prefix+' '+item.draft['title'], 'callback_data': 'item:'+item.id.hex}])
        target = parent.hex if parent else project_id.hex
        root = 'p' if parent else 'r'
        pager = []
        if offset:
            pager.append(self.button('السابق', 'Previous', f'bl:{target}:{root}:{max(0,offset-6)}'))
        if len(items) > 6:
            pager.append(self.button('التالي', 'Next', f'bl:{target}:{root}:{offset+6}'))
        if pager:
            rows.append(pager)
        rows += [[self.button('✚ قسم', '✚ Section', f'bnew:{target}:{root}:section'), self.button('✚ نص', '✚ Text', f'bnew:{target}:{root}:text')],
                 [self.button('✚ رابط', '✚ Link', f'bnew:{target}:{root}:url'), self.button('✚ ملف', '✚ File', f'bnew:{target}:{root}:file')],
                 [self.button('🚀 نشر التعديلات', '🚀 Publish changes', 'launchask:'+str(project_id))]]
        if folder:
            rows.append(self.back(project_id, folder.parent_id))
        rows.append([self.button('↩ لوحة البوت', '↩ Bot panel', 'project:'+str(project_id))])
        await self.menu.save_state(MenuState('idle', {}))
        title = self.tr('🗂 مصمم الأزرار', '🗂 Button designer')+'\n'+project.name
        if folder:
            title += '\n'+folder.draft['title']
        title += self.tr('\n\nأضف أقسامًا داخل أقسام، نصوصًا وروابط وملفات. التعديلات مسودات حتى النشر.\nلا نفرض عددًا ثابتًا للأزرار أو الملفات؛ حدود تيليجرام والاستضافة تبقى سارية.',
                         '\n\nBuild nested sections, text, links and files. Edits remain drafts until published.\nNo fixed item/file count quota; Telegram and hosting capacity limits still apply.')
        return self.menu.response(title, rows)

    async def detail(self, item):
        data, raw = item.draft, item.id.hex
        rows = []
        if data['kind'] == 'section':
            rows.append([self.button('🗂 فتح القسم', '🗂 Open section', 'folder:'+raw)])
        if data['kind'] == 'file':
            project = await self.project(item.project_id)
            if project.telegram_username and project.active_version:
                rows.append([{'text': self.tr('📎 رفع أو استبدال الملف داخل بوتك', '📎 Upload or replace in your bot'),
                              'url': 'https://t.me/'+project.telegram_username+'?start=upload_'+raw}])
            else:
                rows.append([self.button('🔗 ربط البوت أولًا', '🔗 Connect bot first', 'connection:'+str(item.project_id))])
        else:
            rows.append([self.button('✏️ تعديل المحتوى', '✏️ Edit content', 'bedit:'+raw)])
        rows.append([self.button('✏️ اسم الزر', '✏️ Button label', 'btitle:'+raw),
                     self.button('🗑 حذف', '🗑 Delete', 'bdel:'+raw)])
        rows.append(self.back(item.project_id, item.parent_id))
        body = data.get('text') or data.get('url') or self.tr('ملف جاهز' if data.get('file_id') else 'انشر البوت ثم افتح رابط الرفع. بعد استلام الملف انشر التعديلات مرة ثانية.',
            'File ready' if data.get('file_id') else 'Publish the bot, open its upload link, then publish again after receiving the file.')
        return self.menu.response('🗂 '+data['title']+'\n\n'+body[:3000], rows)

    async def handle(self, *, text=None, callback=None):
        parts = callback.split(':') if callback else []
        state = await self.manager.store.state()
        if parts and parts[0] in ('buttons', 'folder', 'item', 'bnew', 'bl', 'bedit', 'btitle', 'bdel'):
            action = parts[0]
            if len(parts) != (4 if action in ('bnew','bl') else 2):
                raise ValueError()
            target = UUID(parts[1])
            if action == 'buttons':
                return await self.listing(target)
            if action in ('bnew','bl'):
                if parts[2] not in ('r', 'p'):
                    raise ValueError()
                parent = await self.item(target, write=action == 'bnew') if parts[2] == 'p' else None
                if parent and parent.draft['kind'] != 'section':
                    raise ValueError()
                project_id = parent.project_id if parent else target
                await self.project(project_id, write=action == 'bnew')
                if action == 'bl':
                    offset = int(parts[3])
                    if not 0 <= offset <= 2**31-1:
                        raise ValueError()
                    return await self.listing(project_id, parent.id if parent else None, offset)
                if parts[3] not in ('section','text','url','file'):
                    raise ValueError()
                await self.menu.save_state(MenuState('button_title', {'project_id':str(project_id),
                    'parent_id':str(parent.id) if parent else None,'kind':parts[3]}))
                return self.menu.response(self.tr('✏️ اسم الزر\n\nاكتب الاسم الذي يظهر للزائر، حتى 64 حرفًا.',
                    '✏️ Button label\n\nSend the visitor-facing label, up to 64 characters.'), [self.back(project_id, parent.id if parent else None)])
            item = await self.item(target, write=action not in ('folder','item'))
            if action == 'folder':
                return await self.listing(item.project_id, item.id)
            if action == 'item':
                await self.menu.save_state(MenuState('idle', {}))
                return await self.detail(item)
            if action == 'bdel':
                nonce = uuid4().hex
                await self.menu.save_state(MenuState('button_delete', {'item_id':str(item.id),'nonce':nonce}))
                return self.menu.response(self.tr('حذف الزر؟ إذا كان قسمًا، تختفي محتوياته من الزوار بعد النشر. تظل النسخة المنشورة كما هي إلى ذلك الحين.',
                    'Delete this button? A section and its contents become unavailable to visitors after publication. The live version stays unchanged until then.'),
                    [[self.button('🗑 تأكيد الحذف', '🗑 Confirm deletion', 'bdelete:'+nonce)],self.back(item.project_id,item.parent_id)])
            await self.menu.save_state(MenuState('button_edit', {'item_id':str(item.id),
                'field':'title' if action=='btitle' else 'url' if item.draft['kind']=='url' else 'text'}))
            return self.menu.response(self.tr('أرسل القيمة الجديدة. الاسم حتى 64 حرفًا، والنص حتى 3000 حرف، والرابط يبدأ بـ https://.',
                'Send the replacement: label up to 64 characters, text up to 3000, or an https:// link.'), [self.back(item.project_id,item.parent_id)])
        if callback and callback.startswith('bdelete:'):
            if state.step != 'button_delete' or callback[8:] != state.data.get('nonce'):
                return self.menu.response(self.menu.text('invalid'))
            item = await self.item(UUID(state.data['item_id']), write=True)
            item.deleted = True
            await self.session.flush()
            await self.manager.store.audit('factory.button.deleted',item.project_id,self.manager.store.user.id,self.manager.store.tenant_id)
            return await self.listing(item.project_id,item.parent_id)
        if not text or text.startswith('/') or state.step not in ('button_title','button_body','button_edit'):
            return None
        if re.search(r'\b[0-9]{5,16}:[A-Za-z0-9_-]{20,}\b', text):
            raise InlineBotError('token')
        data = dict(state.data)
        if state.step == 'button_edit':
            item = await self.item(UUID(data['item_id']), write=True)
            field = data['field']
            self.validate(field,text)
            item.draft = {**item.draft,field:text.strip() if field!='text' else text}
        else:
            project_id = UUID(data['project_id'])
            await self.project(project_id,write=True)
            if data.get('parent_id'):
                parent = await self.item(UUID(data['parent_id']),write=True)
                if parent.project_id != project_id or parent.draft['kind'] != 'section':
                    raise ValueError()
            if state.step == 'button_title':
                self.validate('title',text)
                data['title'] = text.strip()
                if data['kind'] in ('text','url'):
                    await self.menu.save_state(MenuState('button_body',data))
                    return self.menu.response(self.tr('أرسل نص الزر، حتى 3000 حرف.' if data['kind']=='text' else 'أرسل الرابط الكامل ويبدأ بـ https://.',
                        'Send the response text, up to 3000 characters.' if data['kind']=='text' else 'Send the complete https:// link.'), [self.back(project_id,UUID(data['parent_id']) if data.get('parent_id') else None)])
            content = {'kind':data['kind'],'title':data['title']}
            if data['kind'] in ('text','url'):
                field = 'text' if data['kind']=='text' else 'url'
                self.validate(field,text)
                content[field]=text
            item = FactoryButtonRecord(id=uuid4(),project_id=project_id,
                parent_id=UUID(data['parent_id']) if data.get('parent_id') else None,draft=content,deleted=False)
            self.session.add(item)
        await self.session.flush()
        await self.manager.store.audit('factory.button.saved',item.project_id,self.manager.store.user.id,self.manager.store.tenant_id)
        await self.menu.save_state(MenuState('idle',{}))
        return await self.detail(item)

    @staticmethod
    def validate(field,value):
        if not value.strip() or len(value) > (64 if field=='title' else 3000):
            raise ValueError()
        if field=='url':
            parsed=urlsplit(value)
            if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in value):
                raise ValueError()
