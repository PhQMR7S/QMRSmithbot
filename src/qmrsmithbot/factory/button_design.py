"""Draft-only menu order, row layout and official Telegram button colors."""
from datetime import UTC

from sqlalchemy import String, cast, func, select

from qmrsmithbot.db.factory_models import FactoryButtonRecord

STYLES = ('primary', 'success', 'danger')


def order_expression(snapshot='draft'):
    content = getattr(FactoryButtonRecord, snapshot)
    original = func.concat(func.to_char(func.timezone('UTC', FactoryButtonRecord.created_at),
                                       'YYYYMMDDHH24MISSUS'),
                           func.replace(cast(FactoryButtonRecord.id, String), '-', ''))
    return func.coalesce(content['sort_key'].astext, original)


def original_key(item):
    return item.created_at.astimezone(UTC).strftime('%Y%m%d%H%M%S%f') + item.id.hex


async def move_button(session, item, direction):
    """Caller locks the tenant-scoped project. Swap one adjacent sibling only."""
    if direction not in ('up', 'down'):
        raise ValueError('Invalid direction')
    current = item.draft.get('sort_key') or original_key(item)
    key = order_expression()
    query = select(FactoryButtonRecord).where(
        FactoryButtonRecord.project_id == item.project_id,
        FactoryButtonRecord.parent_id == item.parent_id,
        FactoryButtonRecord.deleted.is_(False),
        key < current if direction == 'up' else key > current,
    ).order_by(key.desc() if direction == 'up' else key.asc()).limit(1)
    neighbor = await session.scalar(query)
    if neighbor is None:
        return False
    other = neighbor.draft.get('sort_key') or original_key(neighbor)
    item.draft = {**item.draft, 'sort_key':other}
    neighbor.draft = {**neighbor.draft, 'sort_key':current}
    await session.flush()
    return True


def visitor_button(content, item_id):
    result = {'text': content['title']}
    if content['kind'] == 'url':
        result['url'] = content['url']
    else:
        result['callback_data'] = 'b:' + item_id.hex
    if content.get('style') in STYLES:
        result['style'] = content['style']
    return result


def append_visitor_button(rows, content, item_id):
    result = visitor_button(content, item_id)
    if content.get('join_previous') is True and rows and len(rows[-1]) < 3:
        rows[-1].append(result)
    else:
        rows.append([result])
