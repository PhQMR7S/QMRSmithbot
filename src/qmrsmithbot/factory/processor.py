from aiogram.types import Update
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from qmrsmithbot.auth.authorization import AuthorizationDenied
from qmrsmithbot.config import settings
from qmrsmithbot.db.factory_models import FactoryUpdateRecord
from qmrsmithbot.db.session import SessionFactory
from qmrsmithbot.factory.menu import FactoryMenu
from qmrsmithbot.factory.store import factory_store
from qmrsmithbot.projects.service import ProjectStateError


def private_actor(update: Update):
    callback = update.callback_query
    message = callback.message if callback else update.message
    actor = callback.from_user if callback else message.from_user if message else None
    if (message is None or actor is None or actor.is_bot or actor.id <= 0
            or message.chat.type != 'private' or message.chat.id != actor.id):
        return None
    return actor


class FactoryProcessor:
    def __init__(self, sessions=SessionFactory):
        self.sessions = sessions

    async def process(self, update: Update):
        actor = private_actor(update)
        if actor is None:
            return None
        async with self.sessions() as session, session.begin():
            # Serialize menu transitions for one actor; duplicate update IDs cannot create twice.
            await session.execute(select(func.pg_advisory_xact_lock(actor.id)))
            accepted = await session.scalar(insert(FactoryUpdateRecord).values(
                update_id=update.update_id).on_conflict_do_nothing().returning(
                    FactoryUpdateRecord.update_id))
            if accepted is None:
                return None
            store = await factory_store(session, actor)
            menu = FactoryMenu(store, telegram_id=actor.id,
                               admin=actor.id in settings.telegram_factory_admin_ids)
            try:
                response = await menu.handle(
                    text=update.message.text if update.message else None,
                    callback=update.callback_query.data if update.callback_query else None)
            except (AuthorizationDenied, ProjectStateError):
                response = menu.response(menu.text('invalid'))
            # The transaction is committed before Telegram gets its response command.
        return {'method': 'sendMessage', 'chat_id': actor.id, **response}
