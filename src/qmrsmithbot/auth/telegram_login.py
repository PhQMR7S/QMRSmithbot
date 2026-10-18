"""Browser possession + explicit approval through the authenticated factory webhook."""
import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import func, select, text

from qmrsmithbot.auth.service import SessionService
from qmrsmithbot.config import settings
from qmrsmithbot.db.factory_models import TelegramLoginChallengeRecord
from qmrsmithbot.db.models import AuditEvent
from qmrsmithbot.request_context import get_request_id


class TelegramLoginError(ValueError):
    pass


def factory_bot_id():
    prefix, separator, _ = settings.telegram_factory_bot_token.get_secret_value().partition(':')
    if not separator or not prefix.isascii() or not prefix.isdigit() or int(prefix) <= 0:
        raise TelegramLoginError('Telegram login is unavailable')
    return int(prefix)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class TelegramLoginService:
    def __init__(self, session):
        self.session = session

    async def begin(self):
        if not settings.auth_telegram_enabled:
            raise TelegramLoginError('Telegram login is unavailable')
        now = await self.session.scalar(select(func.clock_timestamp()))
        # Bound retention work. No raw codes, browser secrets or update payloads are stored.
        await self.session.execute(text('''DELETE FROM telegram_login_challenges WHERE id IN (
            SELECT id FROM telegram_login_challenges
            WHERE expires_at < statement_timestamp() - interval '1 hour'
            ORDER BY expires_at LIMIT 100 FOR UPDATE SKIP LOCKED)'''))
        challenge_id, secret = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
        code = f'{secrets.randbelow(1_000_000):06d}'
        record = TelegramLoginChallengeRecord(id=challenge_id,
            browser_secret_hash=digest(secret), code_hash=digest(challenge_id + ':' + code),
            bot_id=factory_bot_id(), attempts=0, expires_at=now + timedelta(minutes=5))
        self.session.add(record)
        await self.session.flush()
        return {'challenge_id': challenge_id, 'browser_secret': secret,
                'verification_code': code, 'expires_at': record.expires_at,
                'telegram_url': f'https://t.me/{settings.telegram_factory_username}?start=login_{challenge_id}'}

    async def _active(self, challenge_id):
        record = await self.session.scalar(select(TelegramLoginChallengeRecord).where(
            TelegramLoginChallengeRecord.id == challenge_id).with_for_update())
        now = await self.session.scalar(select(func.clock_timestamp()))
        if (record is None or record.consumed_at is not None or record.expires_at <= now
                or (record.attempts >= 5 and record.approved_user_id is None)
                or record.bot_id != factory_bot_id()):
            raise TelegramLoginError('Invalid or expired login request')
        return record, now

    async def bind(self, challenge_id, telegram_user_id):
        record, _ = await self._active(challenge_id)
        if record.approved_user_id is not None or record.telegram_user_id not in (None, telegram_user_id):
            raise TelegramLoginError('Invalid or expired login request')
        record.telegram_user_id = telegram_user_id
        await self.session.flush()

    async def approve(self, challenge_id, *, telegram_user_id, user_id, code):
        record, _ = await self._active(challenge_id)
        if record.telegram_user_id != telegram_user_id or record.approved_user_id is not None:
            raise TelegramLoginError('Invalid or expired login request')
        record.attempts += 1
        valid = hmac.compare_digest(record.code_hash, digest(challenge_id + ':' + code))
        if valid:
            record.approved_user_id = user_id
            self.session.add(AuditEvent(actor_user_id=user_id, action='auth.telegram.approved',
                                        request_id=get_request_id()))
        await self.session.flush()
        return valid

    async def finish(self, challenge_id, browser_secret, *, user_agent=None, ip_address=None):
        record, now = await self._active(challenge_id)
        if not hmac.compare_digest(record.browser_secret_hash, digest(browser_secret)):
            raise TelegramLoginError('Invalid or expired login request')
        if record.approved_user_id is None:
            return None
        record.consumed_at = now
        principal, token, expires_at = await SessionService(self.session).create_session(
            user_id=record.approved_user_id, user_agent=user_agent, ip_address=ip_address)
        self.session.add(AuditEvent(actor_user_id=principal.user_id, action='auth.telegram.session_created',
            request_id=get_request_id(), metadata_json={'session_id': str(principal.session_id)}))
        await self.session.flush()
        return {'access_token': token, 'token_type': 'bearer', 'expires_at': expires_at,
                'session_id': principal.session_id}

    async def cancel(self, challenge_id, browser_secret):
        record, now = await self._active(challenge_id)
        if not hmac.compare_digest(record.browser_secret_hash, digest(browser_secret)):
            raise TelegramLoginError('Invalid or expired login request')
        record.consumed_at = now
        await self.session.flush()
