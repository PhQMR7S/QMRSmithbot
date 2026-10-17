import re

from qmrsmithbot.auth.telegram_login import TelegramLoginError, TelegramLoginService
from qmrsmithbot.config import settings
from qmrsmithbot.factory.menu import MenuState

COPY = {
    'ar': {
        'prompt': '🔐 تسجيل الدخول إلى لوحة QMRSmithbot\nأرسل رمز الأرقام الستة الظاهر في المتصفح. '
                  'إذا لم تبدأ الطلب، استخدم /cancel. ينتهي الطلب خلال 5 دقائق.',
        'invalid': 'الطلب منتهي أو غير متاح. ابدأ تسجيل دخول جديدًا من المتصفح.',
        'wrong': 'الرمز غير صحيح. أرسل الرمز الظاهر في المتصفح أو /cancel للإلغاء.',
        'done': '✅ تم تأكيد هويتك. ارجع إلى المتصفح واضغط «إكمال الدخول».',
    },
    'en': {
        'prompt': '🔐 Sign in to QMRSmithbot\nSend the six-digit code shown in your browser. '
                  'If you did not start this request, use /cancel. Requests expire after 5 minutes.',
        'invalid': 'This request expired or is unavailable. Start a new login in your browser.',
        'wrong': 'Incorrect code. Send the code shown in your browser or /cancel.',
        'done': '✅ Identity confirmed. Return to your browser and select Complete sign-in.',
    },
}


async def handle_web_login(session, store, *, telegram_id, message_text):
    if not settings.auth_telegram_enabled or not message_text:
        return None
    language = await store.language()
    copy = COPY[language]
    service = TelegramLoginService(session)
    parts = message_text.split(maxsplit=1)
    if len(parts) == 2 and parts[0] == '/start' and parts[1].startswith('login_'):
        challenge_id = parts[1][6:]
        try:
            if not re.fullmatch(r'[A-Za-z0-9_-]{32}', challenge_id):
                raise TelegramLoginError()
            await service.bind(challenge_id, telegram_id)
        except TelegramLoginError:
            return {'text': copy['invalid']}
        await store.save_state(MenuState('web_login', {'challenge_id': challenge_id}))
        return {'text': copy['prompt']}
    if message_text.startswith('/'):
        return None  # Existing /cancel and /start retain their normal behavior.
    state = await store.state()
    if state.step != 'web_login':
        return None
    try:
        valid = await service.approve(state.data['challenge_id'], telegram_user_id=telegram_id,
                                     user_id=store.user.id, code=message_text.strip())
    except TelegramLoginError:
        await store.save_state(MenuState('idle', {}))
        return {'text': copy['invalid']}
    if not valid:
        return {'text': copy['wrong']}
    await store.save_state(MenuState('idle', {}))
    return {'text': copy['done']}
