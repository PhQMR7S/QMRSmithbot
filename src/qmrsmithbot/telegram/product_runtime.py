"""Button menus and private owner/visitor contact routing."""
from uuid import UUID

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import select

from qmrsmithbot.db.factory_models import (
    BotOwnerStateRecord,
    ContactBlockRecord,
    ContactDeliveryRecord,
    FactoryButtonRecord,
)
from qmrsmithbot.db.models import IdentityRecord
from qmrsmithbot.factory.button_design import append_visitor_button, order_expression
from qmrsmithbot.telegram.client import TelegramBotClientFactory
from qmrsmithbot.telegram.inline_runtime import InlineBotError

FILE_TYPES = ('animation', 'video_note', 'sticker', 'photo', 'video', 'audio', 'voice', 'document')
FILE_METHODS = {kind: 'send' + ''.join(word.title() for word in kind.split('_')) for kind in FILE_TYPES}


def file_reference(message):
    # Telegram file identifiers are bot-scoped. This function runs on the child bot only.
    for kind in FILE_TYPES:
        item = getattr(message, kind, None)
        if item:
            if kind == 'photo':
                item = item[-1]
            return {'file_type': kind, 'file_id': item.file_id,
                    'caption': (message.caption or '')[:1024]}
    return None


def say(chat_id, text, rows=None):
    result = {'method': 'sendMessage', 'chat_id': chat_id, 'text': text}
    if rows:
        result['reply_markup'] = {'inline_keyboard': rows}
    return result


def button(text, data):
    return {'text': text[:64], 'callback_data': data}


async def owner_telegram_id(session, project):
    subject = await session.scalar(select(IdentityRecord.subject).where(
        IdentityRecord.user_id == project.owner_id, IdentityRecord.provider == 'telegram'))
    if subject is None or not subject.isascii() or not subject.isdigit() or int(subject) <= 0:
        raise InlineBotError('Owner Telegram identity is unavailable')
    return int(subject)


async def published_button(session, project_id, item_id):
    row = await session.scalar(select(FactoryButtonRecord).where(
        FactoryButtonRecord.project_id == project_id, FactoryButtonRecord.id == item_id))
    if row is None or not row.published:
        return None
    # A removed/unpublished parent also makes its descendants unavailable.
    parent, visited = row.parent_id, {row.id}
    while parent is not None:
        if parent in visited:
            return None
        visited.add(parent)
        ancestor = await session.scalar(select(FactoryButtonRecord).where(
            FactoryButtonRecord.id == parent, FactoryButtonRecord.project_id == project_id))
        if ancestor is None or not ancestor.published or ancestor.published['kind'] != 'section':
            return None
        parent = ancestor.parent_id
    return row


async def button_page(session, project, welcome, parent_id=None, offset=0):
    parent = None
    if parent_id is not None:
        parent = await published_button(session, project.id, parent_id)
        if parent is None or parent.published['kind'] != 'section':
            return None
    query = select(FactoryButtonRecord).where(FactoryButtonRecord.project_id == project.id,
        FactoryButtonRecord.parent_id == parent_id, FactoryButtonRecord.published.is_not(None))
    # SQL NULL is used when unpublishing; JSON null is excluded as well.
    query = query.order_by(order_expression('published'), FactoryButtonRecord.id).offset(offset).limit(9)
    items = (await session.scalars(query)).all()
    rows = []
    for item in items[:8]:
        content = item.published
        if not content or (content['kind'] == 'file' and not content.get('file_id')):
            continue
        append_visitor_button(rows, content, item.id)
    root = parent_id.hex if parent_id else 'root'
    pager = []
    if offset:
        pager.append(button('السابق', f'pg:{root}:{max(0,offset-8)}'))
    if len(items) > 8:
        pager.append(button('التالي', f'pg:{root}:{offset+8}'))
    if pager:
        rows.append(pager)
    if parent:
        back = parent.parent_id.hex if parent.parent_id else 'root'
        rows.append([button('↩ رجوع', f'pg:{back}:0'), button('⌂ الرئيسية', 'pg:root:0')])
    return say(0, parent.published.get('text') or parent.published['title'] if parent else welcome, rows)


async def product_response(session, project, program, update):
    callback = update.callback_query
    message = callback.message if callback else update.message
    actor = callback.from_user if callback else message.from_user if message else None
    if (message is None or actor is None or actor.is_bot or message.chat.type != 'private'
            or message.chat.id != actor.id):
        return None
    owner = await owner_telegram_id(session, project)
    is_owner = actor.id == owner
    text = message.text if not callback else None
    if program.kind == 'buttons':
        return await buttons_response(session, project, program, message, actor.id, is_owner, text, callback)
    return await contact_response(session, project, program, message, actor.id, owner, text, callback)


async def buttons_response(session, project, program, message, actor_id, is_owner, text, callback):
    if is_owner and text and text.startswith('/start upload_'):
        try:
            item_id = UUID(text.split('upload_', 1)[1])
        except ValueError:
            return say(actor_id, 'رابط الرفع غير صالح.')
        item = await session.scalar(select(FactoryButtonRecord).where(FactoryButtonRecord.id == item_id,
            FactoryButtonRecord.project_id == project.id, FactoryButtonRecord.deleted.is_(False)))
        if item is None or item.draft.get('kind') != 'file':
            return say(actor_id, 'زر الملف غير متاح.')
        state = await session.get(BotOwnerStateRecord, project.id)
        if state is None:
            state = BotOwnerStateRecord(project_id=project.id)
            session.add(state)
        state.data = {**(state.data or {}), 'upload': str(item_id), 'control': {'step':'idle','data':{}}}
        return say(actor_id, '📎 أرسل الملف أو الصورة أو الفيديو أو الصوت هنا. سيُحفظ لهذا الزر كمسودة؛ بعدها افتح /admin وانشر التعديلات. /cancel للإلغاء.')
    if is_owner:
        state = await session.get(BotOwnerStateRecord, project.id)
        if text == '/cancel' and state:
            state.data = {}
            return say(actor_id, 'تم إلغاء الرفع.')
        if state and state.data.get('upload') and not (text or '').startswith('/'):
            item = await session.scalar(select(FactoryButtonRecord).where(
                FactoryButtonRecord.id == UUID(state.data['upload']), FactoryButtonRecord.project_id == project.id,
                FactoryButtonRecord.deleted.is_(False)))
            file = file_reference(message)
            if item is None:
                state.data = {}
                return say(actor_id, 'الزر غير متاح. افتح /admin واختر زر الملف مجددًا.')
            if file is None:
                return say(actor_id, 'أرسل ملفًا أو صورة أو فيديو أو صوتًا أو ملصقًا، أو /cancel.')
            item.draft = {**item.draft, **file}
            state.data = {}
            return say(actor_id, '✅ استلمت الملف داخل بوتك. افتح /admin واضغط نشر لتطبيقه على الزوار.')
    parent_id, offset = None, 0
    selected = None
    if callback:
        data = callback.data or ''
        try:
            if data.startswith('b:'):
                selected = await published_button(session, project.id, UUID(data[2:]))
                if selected is None:
                    return say(actor_id, 'هذا الزر غير متاح الآن. أرسل /start لعرض القائمة.')
                content = selected.published
                if content['kind'] == 'section':
                    parent_id = selected.id
                elif content['kind'] == 'text':
                    parent = selected.parent_id.hex if selected.parent_id else 'root'
                    return say(actor_id, content['text'], [[button('↩ القائمة', f'pg:{parent}:0')]])
                elif content['kind'] == 'file' and content.get('file_id'):
                    result = {'method': FILE_METHODS[content['file_type']], 'chat_id': actor_id,
                              content['file_type']: content['file_id']}
                    if content.get('caption') and content['file_type'] not in ('sticker', 'video_note'):
                        result['caption'] = content['caption']
                    result['reply_markup'] = {'inline_keyboard': [[button('⌂ الرئيسية', 'pg:root:0')]]}
                    return result
                else:
                    return None
            elif data.startswith('pg:'):
                _, raw, page = data.split(':')
                parent_id = None if raw == 'root' else UUID(raw)
                offset = int(page)
                if not 0 <= offset <= 2**31-1:
                    return None
            else:
                return None
        except (ValueError, KeyError):
            return None
    elif not text or text.split()[0].split('@')[0] not in ('/start', '/menu'):
        return say(actor_id, 'اختَر من القائمة أو أرسل /start.')
    result = await button_page(session, project, program.commands['start'], parent_id, offset)
    if result is None:
        return say(actor_id, 'القسم غير متاح. أرسل /start.')
    result['chat_id'] = actor_id
    if callback and getattr(message, 'from_user', None) and message.from_user.id == project.telegram_bot_id and message.text:
        result.update(method='editMessageText', message_id=message.message_id)
    return result


async def contact_response(session, project, program, message, actor_id, owner, text, callback):
    if callback:
        if actor_id != owner:
            return None
        parts = (callback.data or '').split(':')
        if len(parts) != 3 or parts[0] != 'contact' or parts[1] not in ('block', 'unblock'):
            return None
        try:
            visitor = int(parts[2])
            if visitor <= 0 or visitor == owner:
                return None
        except ValueError:
            return None
        # Buttons are actionable only for a visitor already routed to this owner/project.
        exists = await session.scalar(select(ContactDeliveryRecord.owner_message_id).where(
            ContactDeliveryRecord.project_id == project.id, ContactDeliveryRecord.visitor_id == visitor).limit(1))
        if exists is None:
            return None
        blocked = parts[1] == 'block'
        row = await session.get(ContactBlockRecord, (project.id, visitor))
        if row is None:
            row = ContactBlockRecord(project_id=project.id, visitor_id=visitor)
            session.add(row)
        row.blocked = blocked
        opposite = 'unblock' if blocked else 'block'
        return say(owner, '🚫 تم الحظر.' if blocked else '✅ تم إلغاء الحظر.',
            [[button('إلغاء الحظر' if blocked else 'حظر', f'contact:{opposite}:{visitor}')]])
    if text and text.split()[0].split('@')[0] == '/start':
        return say(actor_id, '✉️ هذا بوت تواصلك. ردّ على الرسالة الواردة باستخدام «رد» لإرسال جوابك للزائر.' if actor_id == owner else program.commands['start'])
    if text and text.startswith('/'):
        return say(actor_id, 'أرسل رسالتك أو مرفقك هنا. لصاحب البوت: استخدم «رد» على الرسالة الواردة.')
    if not (message.text or file_reference(message)):
        return say(actor_id, 'هذا النوع غير مدعوم حاليًا. أرسل نصًا أو ملفًا أو صورة أو فيديو أو صوتًا أو ملصقًا.')
    if actor_id == owner:
        replied = message.reply_to_message
        if replied is None:
            return say(owner, 'اختَر «رد» على رسالة الزائر ثم أرسل جوابك؛ لا يمكن الإرسال بدون تحديد الرسالة.')
        route = await session.get(ContactDeliveryRecord, (project.id, replied.message_id))
        if route is None:
            return say(owner, 'لا توجد محادثة مرتبطة بهذه الرسالة.')
        block = await session.get(ContactBlockRecord, (project.id, route.visitor_id))
        if block and block.blocked:
            return say(owner, 'الزائر محظور. ألغِ الحظر قبل الرد.')
        destination, rows = route.visitor_id, None
    else:
        block = await session.get(ContactBlockRecord, (project.id, actor_id))
        if block and block.blocked:
            return say(actor_id, 'التواصل غير متاح لهذا الحساب.')
        destination = owner
        rows = {'inline_keyboard': [[button('🚫 حظر المرسل', f'contact:block:{actor_id}')]]}
    try:
        async with TelegramBotClientFactory(session, timeout=8).bot(project.id) as bot:
            copied = await bot.copy_message(chat_id=destination, from_chat_id=actor_id,
                                           message_id=message.message_id, reply_markup=rows)
    except (TelegramBadRequest, TelegramForbiddenError):
        return say(actor_id, 'تعذّر توصيل الرسالة. قد يكون البوت محظورًا أو الرسالة محمية. جرّب رسالة عادية.')
    except (TelegramAPIError, OSError, TimeoutError):
        raise InlineBotError('Telegram delivery is temporarily unavailable') from None
    # Network/timeouts/429 propagate to request retry; the durable inbox avoids reevaluation after commit.
    if actor_id != owner:
        session.add(ContactDeliveryRecord(project_id=project.id, owner_message_id=copied.message_id,
                                          visitor_id=actor_id))
    return say(actor_id, '✅ تم توصيل الرد.' if actor_id == owner else '✅ وصلت رسالتك لصاحب البوت.')
