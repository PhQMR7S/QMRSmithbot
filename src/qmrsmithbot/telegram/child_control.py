"""Owner-only management inside each child bot, with project-isolated UI state."""
import secrets
from copy import deepcopy

from sqlalchemy import select

from qmrsmithbot.auth.authorization import AuthorizationDenied
from qmrsmithbot.auth.models import Permission
from qmrsmithbot.db.factory_models import BotOwnerStateRecord
from qmrsmithbot.db.models import IdentityRecord, User
from qmrsmithbot.factory.bot_management import BotManagement
from qmrsmithbot.factory.menu import FactoryMenu, MenuState
from qmrsmithbot.factory.presentation import telegram_response
from qmrsmithbot.factory.store import SQLFactoryStore
from qmrsmithbot.projects.service import ProjectStateError
from qmrsmithbot.telegram.inline_runtime import InlineBotError


class ChildStore(SQLFactoryStore):
    child_control = True
    def __init__(self, session, user, project):
        super().__init__(session,user,project.tenant_id)
        self.project_id=project.id

    async def state(self):
        record=await self.session.get(BotOwnerStateRecord,self.project_id)
        value=(record.data or {}).get('control',{}) if record else {}
        return MenuState(value.get('step','idle'),deepcopy(value.get('data',{})))

    async def save_state(self,state):
        record=await self.session.get(BotOwnerStateRecord,self.project_id)
        if record is None:
            record=BotOwnerStateRecord(project_id=self.project_id,data={})
            self.session.add(record)
        record.data={**(record.data or {}),'control':{'step':state.step,'data':deepcopy(state.data)}}
        await self.session.flush()


class ChildManagement(BotManagement):
    async def project(self, project_id, permission=Permission.PROJECT_READ, lock=False):
        if project_id != self.store.project_id:
            raise InlineBotError('missing')
        project=await super().project(project_id,permission,lock)
        if project.owner_id != self.store.user.id:
            raise InlineBotError('missing')
        return project

    async def latest(self,project_id):
        if project_id != self.store.project_id:
            raise InlineBotError('missing')
        return await super().latest(project_id)


ALLOWED = frozenset(('project','buttons','folder','item','bnew','bl','bedit','btitle','bdel',
    'bdelete','bdesign','bd','content','rl','ri','ra','re','rd','ruledeleteok',
    'welcome','preview','simulate','rename','botsettings','profile','health',
    'launchask','launchok','formsetup','forms','fs','fdel','fdelok','contactsetup'))


def localize_panel(response,project,language):
    """Wrap control callbacks, replacing cross-factory navigation with local controls."""
    response=deepcopy(response)
    response['text']=response['text'].replace('نشر آخر مسودة وتشغيل البوت؟ سيُربط بالمصنع ويُستبدل الـWebhook الحالي إن وجد.','نشر آخر مسودة لهذا البوت وتشغيل استقبال الزوار؟').replace('Publish the latest draft and run this bot? This connects it to the factory and replaces any current webhook.','Publish this bot’s latest draft and enable visitor reception?')
    ar=language=='ar'
    rows=[]
    for row in response.get('reply_markup',{}).get('inline_keyboard',[]):
        visible=[]
        for button in row:
            data=button.get('callback_data')
            if data:
                action=data.split(':')[0]
                if action in ('home','projects'):
                    button={'text':'لوحة هذا البوت' if ar else 'This bot’s panel','callback_data':'project:'+str(project.id)}
                elif action in ('connection','managed','bind'):
                    continue
                elif action in ('stopask','resumeask'):
                    button['callback_data']='pause' if action=='stopask' else 'resume'
                elif action not in ALLOWED:
                    continue
                button['callback_data']='ca:'+button['callback_data']
                if len(button['callback_data'].encode())>64:
                    continue
            visible.append(button)
        if visible:
            rows.append(visible)
    rows.append([{'text':'خروج من الإدارة وتجربة البوت' if ar else 'Exit management and try bot',
                  'callback_data':'ca:exit'}])
    response['reply_markup']={'inline_keyboard':rows}
    return response


async def child_control(session,project,update,cached=None):
    callback=update.callback_query
    message=callback.message if callback else update.message
    actor=callback.from_user if callback else message.from_user if message else None
    text=message.text if message and not callback else None
    data=callback.data if callback else None
    enter=bool(text and text.strip()=='/start admin') or bool(text and text.split()[0].split('@')[0]=='/admin')
    explicit=bool(data and data.startswith('ca:')) or enter
    if not message or message.chat.type!='private' or not actor or actor.is_bot or message.chat.id!=actor.id:
        return explicit,None
    if data and data.startswith('ca:') and (not message.from_user or not message.from_user.is_bot or
                                           message.from_user.id!=project.telegram_bot_id):
        return True,None
    record=await session.get(BotOwnerStateRecord,project.id)
    control=(record.data or {}).get('control',{}) if record else {}
    if not explicit and control.get('step','idle')=='idle':
        return False,None
    owner=await session.scalar(select(IdentityRecord.subject).where(IdentityRecord.user_id==project.owner_id,
                                                                  IdentityRecord.provider=='telegram'))
    if owner != str(actor.id):
        return explicit,None
    if cached is not None:
        return True,cached.response
    user=await session.get(User,project.owner_id)
    store=ChildStore(session,user,project)
    manager=ChildManagement(store)
    menu=FactoryMenu(store,telegram_id=actor.id,management=manager)
    menu.lang=await store.language()
    action=data[3:] if data and data.startswith('ca:') else None
    if enter or text=='/cancel':
        if record and record.data.get('upload'):
            record.data={key:value for key,value in record.data.items() if key!='upload'}
        action='project:'+str(project.id)
        text=None
    if action=='exit' or text=='/start':
        await store.save_state(MenuState('idle',{}))
        if text=='/start':
            return False,None
        return True,{'method':'sendMessage','chat_id':actor.id,'text':
            'خرجت من الإدارة. أرسل /start لتجربة البوت، أو /admin للعودة.' if menu.lang=='ar' else
            'Management closed. Send /start to try the bot, or /admin to return.'}
    try:
        if action in ('pause','resume'):
            nonce=secrets.token_hex(12)
            await store.save_state(MenuState('child_running',{'nonce':nonce,'running':action=='resume'}))
            response=menu.response('تأكيد تغيير استقبال الزوار؟' if menu.lang=='ar' else 'Confirm changing visitor reception?',
                [[{'text':'تأكيد' if menu.lang=='ar' else 'Confirm','callback_data':'applylocal:'+nonce}],
                 [{'text':'رجوع' if menu.lang=='ar' else 'Back','callback_data':'project:'+str(project.id)}]])
            # One-time confirmation remains exclusive to this child bot's state.
            response['reply_markup']['inline_keyboard'][0][0]['callback_data']='ca:'+response['reply_markup']['inline_keyboard'][0][0]['callback_data']
            response['reply_markup']['inline_keyboard'][1][0]['callback_data']='ca:project:'+str(project.id)
            return True,telegram_response(response,actor_id=actor.id,callback=callback,bot_id=project.telegram_bot_id)
        if action and action.startswith('applylocal:'):
            state=await store.state()
            if state.step!='child_running' or action.split(':',1)[1]!=state.data.get('nonce'):
                raise InlineBotError('stale')
            await store.set_running(project.id,state.data['running'])
            action='project:'+str(project.id)
        if action and action.split(':')[0] not in ALLOWED:
            raise InlineBotError('missing')
        if action:
            text=None
        response=await manager.handle(menu,text=text,callback=action)
        if response is None:
            response=menu.response('استخدم الأزرار أو /cancel للعودة.' if menu.lang=='ar' else 'Use the controls or /cancel to return.')
    except (AuthorizationDenied,ProjectStateError,InlineBotError,ValueError):
        response=menu.response('هذا الإجراء غير متاح. أرسل /admin لفتح لوحة بوتك.' if menu.lang=='ar' else
                               'Action unavailable. Send /admin to open this bot’s panel.')
    return True,telegram_response(localize_panel(response,project,menu.lang),actor_id=actor.id,
                                 callback=callback,bot_id=project.telegram_bot_id)


async def add_owner_entry(session,project,update,response):
    message=update.message
    if (not response or not message or message.chat.type!='private' or not message.from_user or
            message.from_user.is_bot or message.chat.id!=message.from_user.id or
            (message.text or '').split('@')[0]!='/start'):
        return response
    owner=await session.scalar(select(IdentityRecord.subject).where(
        IdentityRecord.user_id==project.owner_id,IdentityRecord.provider=='telegram'))
    if owner!=str(message.from_user.id):
        return response
    response=deepcopy(response)
    response.setdefault('reply_markup',{'inline_keyboard':[]})['inline_keyboard'].append([
        {'text':'إدارة هذا البوت · Admin','callback_data':'ca:project:'+str(project.id)}])
    return response
