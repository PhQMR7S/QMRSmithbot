"""Native Telegram presentation; user content is always escaped before formatting."""
from copy import deepcopy
from html import escape


def styled_response(text, rows):
    rows = deepcopy(rows)
    for row in rows:
        for button in row:
            action = button.get('callback_data', '').split(':')[0]
            if action in ('create', 'confirm', 'launchok', 'ruleadd', 'ruledone', 'ra', 'wizarddone'):
                button['style'] = 'success'
            elif action in ('stopask', 'ruledelete', 'ruledeleteok', 'rd'):
                button['style'] = 'danger'
            elif action in ('projects', 'project', 'content', 'launchask'):
                button['style'] = 'primary'
    return {'text': text, 'reply_markup': {'inline_keyboard': rows}}


def telegram_response(response, *, actor_id, callback, bot_id, rich=False, language="ar"):
    result = {'method': 'sendMessage', 'chat_id': actor_id, **response}
    message = callback.message if callback else None
    # Only edit a visible message authored by this factory, never user-authored content.
    if (message and message.message_id > 0 and getattr(message, 'from_user', None)
            and message.from_user.is_bot and message.from_user.id == bot_id):
        result.update(method='editMessageText', message_id=message.message_id)
    if rich:
        text = result.pop('text')
        title, separator, body = text.partition('\n')
        html = '<h2>' + escape(title) + '</h2>'
        if separator and body.strip():
            html += '<p>' + escape(body).replace('\n', '<br>') + '</p>'
        result['rich_message'] = {'html': html, 'is_rtl': language == 'ar', 'skip_entity_detection': True}
        if result['method'] == 'sendMessage':
            result['method'] = 'sendRichMessage'
    return result
