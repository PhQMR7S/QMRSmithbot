from types import SimpleNamespace

from aiogram.methods import EditMessageText, SendMessage, SendRichMessage
from aiogram.types import InlineKeyboardMarkup

from qmrsmithbot.factory.presentation import styled_response, telegram_response


def test_modern_buttons_validate_against_current_telegram_models():
    response = styled_response('Menu', [[{'text': 'Create', 'callback_data': 'create'},
        {'text': 'Delete', 'callback_data': 'rd:abc:1:0'}]])
    markup = InlineKeyboardMarkup.model_validate(response['reply_markup'])
    assert markup.inline_keyboard[0][0].style == 'success'
    assert markup.inline_keyboard[0][1].style == 'danger'


def test_navigation_edits_only_factory_authored_messages():
    response = styled_response('Menu', [[{'text': 'Home', 'callback_data': 'home'}]])
    message = SimpleNamespace(message_id=55, from_user=SimpleNamespace(id=99, is_bot=True))
    callback = SimpleNamespace(message=message)
    command = telegram_response(response, actor_id=42, callback=callback, bot_id=99)
    assert command['method'] == 'editMessageText' and command['message_id'] == 55
    EditMessageText.model_validate(command)
    message.from_user.id = 98
    command = telegram_response(response, actor_id=42, callback=callback, bot_id=99)
    assert command['method'] == 'sendMessage'
    SendMessage.model_validate(command)


def test_rich_rendering_escapes_user_markup_and_supports_rtl():
    response = styled_response('<script>Title</script>\n<a href="bad">content</a>', [[{'text': 'Home', 'callback_data': 'home'}]])
    command = telegram_response(response, actor_id=42, callback=None, bot_id=99, rich=True)
    assert command['method'] == 'sendRichMessage'
    assert '<script>' not in command['rich_message']['html']
    assert '<a href=' not in command['rich_message']['html']
    assert command['rich_message']['is_rtl'] is True
    SendRichMessage.model_validate(command)
