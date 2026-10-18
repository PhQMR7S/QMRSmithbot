"""An honest distinction between SDK/API features and implemented product tools."""


def feature_guide(language='ar',child=False):
    if language=='ar':
        body=('ميزات تيليجرام في النظام\n\n'
              'متاحة الآن\n'
              '• لوحات خاصة بصاحب كل بوت، وتحرير ونشر من داخله.\n'
              '• أزرار ملوّنة وصفوف وترتيب وأقسام وملفات.\n'
              '• تواصل خاص مع مرفقات ورد مرتبط وحظر المرسل.\n'
              '• نماذج بأسئلة وخيارات وحدود وتفرعات وصندوق إجابات.\n'
              '• رسائل إدارة غنية اختيارية، مع عرض نصي بديل.\n'
              '• إنشاء بوت مُدار عند تفعيل Bot Management Mode، أو الربط بالتوكن.\n\n'
              'تحتاج توسعة وإعدادًا قبل الاستخدام\n'
              'Mini Apps، المدفوعات والاشتراكات، إدارة المجموعات وطلبات الانضمام، Business/Secretary Bots، المجتمعات، الرسائل المؤقتة، البث الذكي، الاستطلاعات والاختبارات، وواجهات الذكاء الاصطناعي. هذه ليست أدوات مفعّلة حاليًا.\n\n'
              'دعم الحقول داخل المكتبة لا يعني أن الميزة مطبّقة في القوالب. ظهور الألوان والرسائل الغنية يعتمد على نسخة تيليجرام. الأيقونات المخصصة قد تتطلب أهلية Premium/Fragment. لا يتم تفعيل خدمة مدفوعة تلقائيًا.')
    else:
        body=('Telegram features in this product\n\n'
              'Available now\n'
              '• Owner-only child dashboards with editing and publication.\n'
              '• Colored buttons, rows, ordering, nested sections and files.\n'
              '• Private contact, attachments, linked replies and blocking.\n'
              '• Forms, choices, numeric limits, forward branches and submissions.\n'
              '• Optional rich management messages and a plain fallback.\n'
              '• Managed-bot creation when enabled, or token binding.\n\n'
              'Require additional implementation and setup\n'
              'Mini Apps, payments/subscriptions, group and join-request management, Business/Secretary Bots, communities, ephemeral messages, campaigns, polls/quizzes and AI integrations are not currently enabled tools.\n\n'
              'SDK fields do not imply implemented template support. Colors/rich messages depend on the Telegram client. Custom emoji may require Premium/Fragment eligibility. No paid service is enabled automatically.')
    return {'text':body,'reply_markup':{'inline_keyboard':[
        [{'text':'المواصفات الرسمية' if language=='ar' else 'Official Bot API','url':'https://core.telegram.org/bots/api'}],
        [{'text':'إعدادات البوت' if language=='ar' and child else 'Bot settings' if child else 'الرئيسية' if language=='ar' else 'Home',
          'callback_data':'identity' if child else 'home'}]]}}
