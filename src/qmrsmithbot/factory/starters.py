"""Original, editable starter structures. Preview never creates a project."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4


@dataclass(frozen=True)
class Starter:
    id: str
    title: tuple[str, str]
    description: tuple[str, str]
    # parent index, title, optional text; sections have no text.
    items: tuple


STARTERS = (
    Starter('knowledge', ('مكتبة محتوى', 'Content library'),
        ('أقسام متداخلة للدروس والمراجع والأسئلة الشائعة.', 'Nested lessons, resources and frequently asked questions.'), (
        (None, ('الدروس', 'Lessons'), None),
        (0, ('الدرس الأول', 'First lesson'), ('هذا محتوى تجريبي قابل للتعديل. ضع شرح الدرس هنا.', 'Editable sample. Add your lesson here.')),
        (0, ('الدرس الثاني', 'Second lesson'), ('هذا محتوى تجريبي قابل للتعديل. ضع شرح الدرس الثاني هنا.', 'Editable sample. Add your second lesson here.')),
        (None, ('المراجع', 'Resources'), ('أضف أسماء المراجع وروابطها بعد الإنشاء.', 'Add reference names and links after creation.')),
        (None, ('الأسئلة الشائعة', 'Frequently asked questions'), None),
        (4, ('كيف أستخدم المكتبة؟', 'How do I use this library?'), ('اختر قسم الدروس ثم افتح الدرس المطلوب.', 'Open Lessons and choose a lesson.')),
    )),
    Starter('services', ('دليل خدمات', 'Service directory'),
        ('عرض الخدمات وتفاصيلها وخطوات الطلب دون دفع مفعّل.', 'Services, details and request instructions; no payment processing.'), (
        (None, ('الخدمات', 'Services'), None),
        (0, ('الخدمة الأولى', 'First service'), ('محتوى تجريبي: اكتب وصف الخدمة والسعر والشروط الحقيقية هنا.', 'Sample: enter your actual service, price and terms here.')),
        (0, ('الخدمة الثانية', 'Second service'), ('محتوى تجريبي: اكتب وصف الخدمة الثانية هنا.', 'Sample: describe your second service here.')),
        (None, ('طريقة الطلب', 'How to order'), ('عدّل هذه الرسالة وأضف طريقة التواصل الصحيحة قبل النشر. الدفع غير مفعّل في هذا النموذج.', 'Edit this message with your real contact instructions before publishing. Payments are not enabled in this starter.')),
        (None, ('الشروط والمعلومات', 'Terms and information'), ('محتوى تجريبي: أضف شروط الخدمة وسياسة الاسترجاع المناسبة لنشاطك.', 'Sample: add the terms and refund policy appropriate for your service.')),
    )),
    Starter('community', ('دليل مجتمع', 'Community guide'),
        ('تعريف المجتمع والقواعد ومساحة للفعاليات والأسئلة.', 'Community information, rules, events and questions.'), (
        (None, ('عن المجتمع', 'About the community'), ('محتوى تجريبي: عرّف مجتمعك وأهدافه هنا.', 'Sample: introduce your community and its goals.')),
        (None, ('القواعد', 'Community rules'), ('محتوى تجريبي: اكتب القواعد المعتمدة لمجتمعك.', 'Sample: add the rules your community follows.')),
        (None, ('الفعاليات', 'Events'), None),
        (2, ('الفعالية القادمة', 'Next event'), ('محتوى تجريبي: أضف موعد الفعالية وتفاصيل المشاركة.', 'Sample: add your event date and participation details.')),
        (None, ('الأسئلة الشائعة', 'Frequently asked questions'), ('محتوى تجريبي: أضف إجابات الأسئلة المتكررة.', 'Sample: add answers to common questions.')),
    )),
)


def get_starter(key):
    return next((item for item in STARTERS if item.id == key), None)


def starter_records(key, project_id, language):
    from qmrsmithbot.db.factory_models import FactoryButtonRecord
    starter = get_starter(key)
    if starter is None:
        raise ValueError('Unknown starter')
    lang = 0 if language == 'ar' else 1
    ids = [uuid4() for _ in starter.items]
    created = datetime.now(UTC)
    return [FactoryButtonRecord(created_at=created+timedelta(microseconds=i), id=ids[i], project_id=project_id,
                parent_id=ids[parent] if parent is not None else None,
                draft={'kind':'section' if body is None else 'text', 'title':title[lang],
                       **({'text':body[lang]} if body is not None else {})}, deleted=False)
            for i, (parent, title, body) in enumerate(starter.items)]


async def starter_browser(menu, callback):
    if not callback or not callback.startswith(('starters', 'starter:', 'sdemo:', 'suse:')):
        return None
    lang = 0 if menu.lang == 'ar' else 1
    tr = lambda ar, en: ar if lang == 0 else en
    def button(label, data):
        return {'text':label, 'callback_data':data}
    if callback == 'starters':
        return menu.response(tr('ابدأ ببنية جاهزة\n\nعاين تجربة الزائر أولًا، ثم أنشئ نسخة مستقلة وعدّل جميع نصوصها وأقسامها. هذه نماذج أزرار؛ النصوص التجريبية تحتاج مراجعتك قبل النشر.',
            'Start with a ready structure\n\nPreview the visitor journey, then create an independent copy and edit every section. These are button starters; review sample text before publishing.'),
            [[button(s.title[lang], 'starter:'+s.id)] for s in STARTERS] + [[menu.button('back','create')]])
    parts = callback.split(':')
    starter = get_starter(parts[1]) if len(parts) >= 2 else None
    if starter is None:
        return menu.response(menu.text('invalid'))
    if parts[0] == 'suse' and len(parts) == 2:
        from qmrsmithbot.factory.menu import MenuState
        await menu.save_state(MenuState('name', {'template':'buttons', 'starter':starter.id}))
        return await menu.wizard_prompt('name')
    if parts[0] == 'starter' and len(parts) == 2:
        return menu.response(starter.title[lang]+'\n\n'+starter.description[lang]+'\n\n'+tr(
            f'{len(starter.items)} عناصر جاهزة للتعديل. لا يتم إنشاء بوت أو نشره أثناء المعاينة.',
            f'{len(starter.items)} editable items. Preview does not create or publish a bot.'),
            [[button(tr('معاينة تجربة الزائر','Preview visitor journey'),'sdemo:'+starter.id+':root')],
             [button(tr('إنشاء نسختي','Create my copy'),'suse:'+starter.id)],
             [button(tr('كل النماذج','All starters'),'starters')]])
    if parts[0] != 'sdemo' or len(parts) != 3:
        return menu.response(menu.text('invalid'))
    try:
        index = None if parts[2] == 'root' else int(parts[2])
        if index is not None and not 0 <= index < len(starter.items):
            raise ValueError()
    except ValueError:
        return menu.response(menu.text('invalid'))
    selected = starter.items[index] if index is not None else None
    body = selected[2][lang] if selected and selected[2] else tr('اختر قسمًا لاستكشافه.', 'Choose a section to explore.')
    title = selected[1][lang] if selected else starter.title[lang]
    rows = [[button(t[lang], f'sdemo:{starter.id}:{i}')] for i,(parent,t,_) in enumerate(starter.items) if parent == index]
    if selected:
        target = selected[0] if selected[0] is not None else 'root'
        rows.append([button(tr('رجوع داخل النموذج','Back in preview'), f'sdemo:{starter.id}:{target}')])
    rows += [[button(tr('إنشاء نسختي','Create my copy'),'suse:'+starter.id)],
             [button(tr('إنهاء المعاينة','Close preview'),'starter:'+starter.id)]]
    return menu.response(tr('معاينة تجريبية · ', 'Sample preview · ')+title+'\n\n'+body, rows)


def template_detail(menu, key):
    from qmrsmithbot.templates.catalog import get_template
    try:
        template = get_template(key)
    except KeyError:
        return menu.response(menu.text('invalid'))
    ar = menu.lang == 'ar'
    details = {
        'buttons': ('ابنِ قوائم متعددة المستويات، ونصوصًا وروابط وملفات. ابدأ فارغًا أو اختر بنية جاهزة وعدّلها. لا توجد حصة ثابتة لعدد العناصر؛ حدود تيليجرام والاستضافة سارية.',
                    'Build nested menus, texts, links and files. Start empty or customize a starter. No fixed item-count quota; Telegram and hosting limits apply.'),
        'contact': ('رسائل الزوار ومرفقاتهم تصل إلى حسابك داخل بوتك. ترد على الرسالة لتصل الإجابة إلى صاحبها. يتضمن حظر المرسل وإلغاء حظره. ليس نظام تذاكر متعدد الموظفين.',
                    'Receive visitor messages and attachments in your bot. Reply to answer the correct visitor. Sender blocking is included. This is not a multi-agent ticket system.'),
        'form': ('أسئلة نصية ورقمية واختيارات، مع تخطي الاختياري وتفرعات للأمام وصندوق إجابات خاص بصاحب البوت. من سؤال واحد إلى 20 سؤالًا. بيانات النموذج مسودة حتى تنشرها.',
                 'Text, number and choice questions, optional skips, forward branches and an owner-only inbox. Supports 1–20 questions. Changes remain drafts until published.'),
        'welcome': ('رسالة بداية بسيطة تظهر عند /start. مناسب للتعريف، ولا يتضمن قوائم أو جمع طلبات.',
                    'A simple /start greeting. Useful for introductions; does not include menus or request collection.'),
        'auto-replies': ('ردود مخصصة لعبارات محددة يرسلها الزائر. المطابقة نصية؛ هذا القالب لا يستخدم ذكاءً اصطناعيًا لفهم النية.',
                         'Custom responses to exact visitor phrases. This template uses text matching, not AI intent detection.'),
        'command-menu': ('أوامر مخصصة مثل /help مع رد لكل أمر. تُحفظ وتُعاين قبل النشر.',
                         'Custom commands such as /help with individual responses. Save and preview before publishing.'),
    }
    rows = [[{'text':'إنشاء هذا النوع' if ar else 'Create this bot type', 'callback_data':'template:'+key}]]
    if key == 'buttons':
        rows.insert(0,[{'text':'اختيار بنية جاهزة ومعاينتها' if ar else 'Choose and preview a starter', 'callback_data':'starters'}])
    rows.append([{'text':'كل أنواع البوتات' if ar else 'All bot types', 'callback_data':'create'}])
    return menu.response((template.title_ar if ar else template.title_en)+'\n\n'+details[key][0 if ar else 1]+('\n\nبعد الإنشاء: خصّص المحتوى، اربط بوتك، جرّبه ثم انشره.' if ar else '\n\nAfter creation: customize, connect, test and publish.'),rows)
