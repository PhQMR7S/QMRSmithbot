"""Native Telegram creation, with owner confirmation before credential binding."""
from time import time
from urllib.parse import urlencode
from uuid import UUID, uuid4

from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select

from qmrsmithbot.config import settings
from qmrsmithbot.db.factory_models import TelegramInlineBotRecord
from qmrsmithbot.db.models import BotCredentialRecord, BotProjectRecord
from qmrsmithbot.factory.menu import MenuState
from qmrsmithbot.telegram.inline_runtime import InlineBotError
from qmrsmithbot.telegram.product_runtime import owner_telegram_id

PENDING_SECONDS = 600


def pending_valid(state):
    return (state.step == 'managed_wait' and isinstance(state.data.get('expires'), (int, float))
            and time() < state.data['expires'])


def creation_url(manager, name):
    return 'https://t.me/newbot/' + manager + '/QMR_' + uuid4().hex[:12] + '_bot?' + urlencode({'name': name[:64]})


async def prepare_creation(management, menu, project):
    from qmrsmithbot.factory.bot_management import make_bot
    if project.owner_id != management.store.user.id or project.telegram_bot_id is not None:
        raise InlineBotError('assigned')
    bot = make_bot(settings.telegram_factory_bot_token.get_secret_value())
    try:
        me = await bot.get_me()
    except (TelegramAPIError, OSError, TimeoutError, RuntimeError):
        raise InlineBotError('unavailable') from None
    finally:
        await bot.session.close()
    if not me.can_manage_bots or not me.username:
        return menu.response('⚙️ يلزم تفعيل Bot Management Mode للمصنع من إعداداته داخل تطبيق @BotFather. يمكنك حاليًا ربط توكن بوتك.',
            [[{'text': '🔗 ربط توكن جاهز', 'callback_data': 'bind:' + str(project.id)}]])
    await menu.save_state(MenuState('managed_wait', {'project_id': str(project.id), 'expires': time() + PENDING_SECONDS}))
    return menu.response('✨ أنشئ بوتك من نافذة تيليجرام. بعد الإنشاء ارجع هنا لتأكيد ربطه بهذا المشروع. تنتهي هذه الخطوة بعد 10 دقائق.',
        [[{'text': '✨ إنشاء بوت داخل تيليجرام', 'url': creation_url(me.username, project.name)}],
         [{'text': '↩ إلغاء', 'callback_data': 'project:' + str(project.id)}]])


async def receive_managed(management, menu, event):
    """Only authenticated managed_bot updates supply bot IDs; callbacks never do."""
    if event.user.is_bot or not event.bot_user.is_bot or event.user.id != menu.telegram_id:
        return None
    existing = await management.session.scalar(select(BotProjectRecord).where(
        BotProjectRecord.telegram_bot_id == event.bot_user.id).with_for_update())
    if existing is not None:
        owner = await owner_telegram_id(management.session, existing)
        if owner != event.user.id:
            # Ownership changes must never leave the previous owner's routing active.
            existing.status = 'error'
            credential = await management.session.get(BotCredentialRecord, existing.id)
            if credential is not None:
                await management.session.delete(credential)
            record = await management.session.get(TelegramInlineBotRecord, existing.id)
            if record is not None:
                record.enabled = False
            return None
        return None  # Rotation is explicitly confirmed through the connection panel.
    state = await management.store.state()
    if not pending_valid(state):
        return None
    project = await management.project(UUID(state.data['project_id']))
    if project.owner_id != management.store.user.id or project.telegram_bot_id is not None:
        return None
    # Reserve the authenticated identity before confirmation so ownership-change
    # events can invalidate a pending connection without retaining credentials.
    project.telegram_bot_id = event.bot_user.id
    project.telegram_username = event.bot_user.username
    nonce = uuid4().hex
    await menu.save_state(MenuState('managed_confirm', {**state.data, 'bot_id': event.bot_user.id,
        'username': event.bot_user.username, 'nonce': nonce}))
    return menu.response('🤖 تم استلام البوت الجديد: @' + (event.bot_user.username or str(event.bot_user.id))
        + '\nالمشروع: ' + project.name + '\n\nتأكيد ربط هذا البوت بالمشروع؟ لن يُنشر المحتوى قبل اختيار «نشر وتشغيل».',
        [[{'text': '✅ تأكيد الربط', 'callback_data': 'managedok:' + nonce}],
         [{'text': '↩ إلغاء', 'callback_data': 'project:' + str(project.id)}]])


async def confirm_binding(management, menu, nonce):
    from qmrsmithbot.factory.bot_management import make_bot
    state = await management.store.state()
    if (state.step != 'managed_confirm' or state.data.get('nonce') != nonce
            or time() >= state.data.get('expires', 0)):
        return menu.response(menu.text('invalid'))
    project_id = UUID(state.data['project_id'])
    project = await management.project(project_id, lock=True)
    if (project.owner_id != management.store.user.id or project.status == 'error'
            or project.telegram_bot_id != state.data['bot_id']):
        raise InlineBotError('missing')
    bot = make_bot(settings.telegram_factory_bot_token.get_secret_value())
    try:
        token = await bot.get_managed_bot_token(user_id=state.data['bot_id'])
    except (TelegramAPIError, OSError, TimeoutError, RuntimeError):
        raise InlineBotError('token') from None
    finally:
        await bot.session.close()
    if token.partition(':')[0] != str(state.data['bot_id']):
        raise InlineBotError('token')
    await management.bind(project_id, token)
    await menu.save_state(MenuState('idle', {}))
    return menu.response('✅ تم ربط البوت. عاين المحتوى، ثم اختر «نشر وتشغيل» من لوحته.',
        [[{'text': '🎛 لوحة تحكم البوت', 'callback_data': 'project:' + str(project_id)}]])
