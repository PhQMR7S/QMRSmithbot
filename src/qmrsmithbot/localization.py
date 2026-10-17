"""Shared UI language metadata and deterministic locale resolution."""
from typing import Literal

LanguageCode = Literal['ar', 'en']
DEFAULT_LANGUAGE: LanguageCode = 'ar'
LANGUAGES = {
    'ar': {'code': 'ar', 'name': 'العربية', 'direction': 'rtl'},
    'en': {'code': 'en', 'name': 'English', 'direction': 'ltr'},
}
MESSAGES = {
    'ar': {'home': 'مصنع البوتات', 'create_bot': 'إنشاء بوت', 'my_bots': 'بوتاتي',
           'settings': 'الإعدادات', 'language': 'اللغة', 'saved': 'تم الحفظ',
           'cancel': 'إلغاء', 'back': 'رجوع', 'support': 'الدعم الفني'},
    'en': {'home': 'Bot Factory', 'create_bot': 'Create bot', 'my_bots': 'My bots',
           'settings': 'Settings', 'language': 'Language', 'saved': 'Saved',
           'cancel': 'Cancel', 'back': 'Back', 'support': 'Support'},
}


def resolve_language(preference: str | None, hint: str | None = None) -> LanguageCode:
    """Explicit supported preference wins over platform hint; Arabic is fallback."""
    for value in (preference, hint):
        if isinstance(value, str):
            primary = value.strip().replace('_', '-').split('-', 1)[0].lower()
            if primary == 'ar':
                return 'ar'
            if primary == 'en':
                return 'en'
    return DEFAULT_LANGUAGE
