"""Credential-free, bilingual diagnostics; no Telegram error strings are echoed."""
from datetime import UTC, datetime


def describe_connection(*, language, identity_matches, webhook_matches, has_webhook,
                        pending, last_error, elapsed_ms, running):
    def tr(ar, en):
        return ar if language == 'ar' else en

    rows = [tr('فحص اتصال البوت', 'Bot connection check')]
    rows.append(tr('هوية البوت: مطابقة', 'Bot identity: matches') if identity_matches else
                tr('تحذير: هوية التوكن لا تطابق البوت المرتبط', 'Warning: token identity differs from the connected bot'))
    if webhook_matches:
        rows.append(tr('Webhook: متصل بالمصنع', 'Webhook: connected to the factory'))
    elif has_webhook:
        rows.append(tr('Webhook: موجّه إلى عنوان مختلف؛ راجع الاتصال قبل النشر',
                       'Webhook: points elsewhere; review the connection before publishing'))
    else:
        rows.append(tr('Webhook: غير مسجل', 'Webhook: not registered'))
    rows.append(tr('التشغيل المحلي: مفعّل' if running else 'التشغيل المحلي: متوقف أو غير منشور',
                   'Local runtime: enabled' if running else 'Local runtime: stopped or unpublished'))
    rows.append(tr(f'التحديثات المعلّقة: {pending}', f'Pending updates: {pending}'))
    if last_error:
        stamp = last_error.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')
        rows.append(tr(f'آخر خطأ تسليم سجّله تيليجرام: {stamp} (قد يكون سابقًا)',
                       f'Last Telegram delivery error: {stamp} (may be historical)'))
    else:
        rows.append(tr('لا يوجد خطأ تسليم مسجل لدى تيليجرام', 'No delivery error recorded by Telegram'))
    rows.append(tr(f'زمن طلبَي الفحص: {elapsed_ms} مللي ثانية', f'Two-request check time: {elapsed_ms} ms'))
    rows.append(tr('هذا زمن الاتصال بتيليجرام، وليس زمن الرد على الزائر. الفحص لا يغيّر Webhook ولا يحذف التحديثات.',
                   'This measures Telegram API access, not visitor response time. The check does not change the webhook or discard updates.'))
    rows.append(tr('وقت الفحص: ', 'Checked: ') + datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC'))
    return '\n'.join(rows)
