"""Presentation settings and a browsable native project library."""
import re

from qmrsmithbot.auth.models import Permission
from qmrsmithbot.factory.menu import MenuState


async def experience(menu, *, text=None, callback=None):
    tr = lambda ar, en: ar if menu.lang == 'ar' else en
    def button(ar, en, data):
        return {'text': tr(ar, en), 'callback_data': data}
    if text == '/plain':
        callback = 'ui:plain'
    elif text == '/appearance':
        callback = 'appearance'
    state = await menu.store.state()
    ui = dict(state.data.get('_ui', {}))
    if callback and callback.startswith('ui:'):
        option = callback[3:]
        if option in ('cards', 'list'):
            ui['layout'] = option
        elif option in ('rich', 'plain'):
            ui['rich'] = option == 'rich'
        else:
            return menu.response(menu.text('invalid'))
        await menu.store.save_state(MenuState('idle', {'_ui': ui}))
        callback = 'appearance'
    if callback == 'appearance':
        layout = ui.get('layout', 'cards')
        rich = ui.get('rich', False)
        return menu.response(tr('🎛 تخصيص تجربتك\n\nاختر عرض بوتاتك وتنسيق اللوحات. تحفظ اختياراتك لحسابك.\nالرسائل الغنية تحتاج نسخة تيليجرام حديثة؛ للرجوع للعرض البسيط بأي وقت أرسل /plain.',
            '🎛 Your experience\n\nChoose your bot layout and panel formatting. Preferences are saved to your account.\nRich messages need a recent Telegram client; send /plain at any time to restore plain mode.'),
            [[button(('✓ ' if layout == 'cards' else '')+'بطاقات', ('✓ ' if layout == 'cards' else '')+'Cards', 'ui:cards'),
              button(('✓ ' if layout == 'list' else '')+'قائمة مختصرة', ('✓ ' if layout == 'list' else '')+'Compact list', 'ui:list')],
             [button(('✓ ' if rich else '')+'رسائل غنية', ('✓ ' if rich else '')+'Rich messages', 'ui:rich'),
              button(('✓ ' if not rich else '')+'عرض بسيط', ('✓ ' if not rich else '')+'Plain messages', 'ui:plain')],
             [button('🤖 عرض بوتاتي', '🤖 View my bots', 'projects:0')], [menu.button('back', 'home')]])
    if callback == 'search':
        await menu.save_state(MenuState('project_search', {}))
        return menu.response(tr('🔎 ابحث عن بوت\n\nاكتب جزءًا من اسم البوت، حتى 120 حرفًا.',
                                '🔎 Find a bot\n\nSend part of its name, up to 120 characters.'))
    if state.step == 'project_search' and text and not text.startswith('/'):
        if re.search(r'\b[0-9]{5,16}:[A-Za-z0-9_-]{20,}\b', text):
            return menu.response(menu.text('invalid'))
        if not 0 < len(text.strip()) <= 120:
            return menu.response(menu.text('invalid'))
        ui['query'] = text.strip()
        await menu.store.save_state(MenuState('idle', {'_ui': ui}))
        callback = 'projects:0'
    if callback and callback.startswith('filter:'):
        value = callback[7:]
        if value not in ('all', 'running', 'stopped', 'draft'):
            return menu.response(menu.text('invalid'))
        ui['filter'], ui['query'] = value, ''
        await menu.store.save_state(MenuState('idle', {'_ui': ui}))
        callback = 'projects:0'
    if not callback or not callback.startswith('projects:'):
        return None
    try:
        offset = int(callback[9:])
        if not 0 <= offset <= 2**31-1:
            raise ValueError()
    except ValueError:
        return menu.response(menu.text('invalid'))
    # This richer browser is enabled only for the SQL-backed factory.
    if menu.management is None:
        return None
    status = ui.get('filter', 'all')
    query = ui.get('query', '')
    await menu.store.permission(Permission.PROJECT_READ)
    projects = await menu.store.projects_service.list_projects(tenant_id=menu.store.tenant_id,
        offset=offset, limit=7, query=query, status=None if status == 'all' else status)
    rows, cards = [], []
    symbols = {'running': '🟢', 'stopped': '⏸', 'draft': '📝', 'error': '⚠️'}
    for index, project in enumerate(projects[:6], offset+1):
        label = f'{symbols.get(project.status, "🤖")} {project.name[:45]}'
        rows.append([{'text': label, 'callback_data': f'project:{project.id}'}])
        cards.append(f'{index}. {project.name[:70]}\n{menu.text(project.status)} · '
                     + tr(f'الإصدار {project.active_version or "—"}', f'Version {project.active_version or "—"}'))
    title = tr('🤖 مكتبة بوتاتك', '🤖 Your bot library')
    if query:
        title += tr('\nبحث: ', '\nSearch: ') + query
    title += '\n' + tr('التصنيف: ', 'Filter: ') + (tr('الكل', 'All') if status == 'all' else menu.text(status))
    body = '\n\n'.join(cards) if ui.get('layout', 'cards') == 'cards' else tr('اختر بوتًا من القائمة أدناه.', 'Choose a bot below.')
    if not projects:
        body = tr('لا توجد بوتات تطابق الاختيار. غيّر التصنيف أو أنشئ بوتك الأول.', 'No matching bots. Change the filter or create your first bot.')
    pager = []
    if offset:
        pager.append(menu.button('prev', f'projects:{max(0, offset-6)}'))
    if len(projects) > 6:
        pager.append(menu.button('next', f'projects:{offset+6}'))
    if pager:
        rows.append(pager)
    rows += [[button('الكل', 'All', 'filter:all'), button('🟢 تعمل', '🟢 Running', 'filter:running'), button('📝 مسودات', '📝 Drafts', 'filter:draft')],
             [button('🔎 بحث', '🔎 Search', 'search'), button('🎛 طريقة العرض', '🎛 Appearance', 'appearance')],
             [menu.button('create', 'create')], [menu.button('back', 'home')]]
    return menu.response(title+'\n\n'+body, rows)
