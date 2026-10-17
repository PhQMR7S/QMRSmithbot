# Telegram sign-in for the dashboard

This optional provider uses the existing factory webhook to approve a browser login. It uses
the same Telegram identity mapping as the factory, so the user sees the same personal workspace
and projects. It never treats an external Telegram ID as an internal account ID, and it does
not merge unrelated OIDC accounts automatically.

## Flow

1. Browser POST /api/v1/auth/telegram/start creates a five-minute challenge, a six-digit
   verification code, and a separate 256-bit browser secret. Only hashes are persisted.
2. The browser shows the code and a Telegram deep link. The code and browser secret are absent
   from the link. Login material stays in page memory and is not written to localStorage.
3. The user opens the factory link. The first authenticated Telegram actor binds the challenge.
   The bot explicitly asks for the browser's code. The user sends it through the protected
   factory webhook. Five wrong attempts lock the challenge; a correct fifth attempt is accepted.
4. The user returns to the browser and selects Complete sign-in. POST /telegram/finish requires
   the separate browser secret. Before approval it returns 202. After approval it locks and
   consumes the challenge, creates one normal revocable session and returns its bearer token.
   Concurrent finish requests cannot create multiple sessions.
5. Cancel request calls POST /telegram/cancel and invalidates the challenge server-side.

The browser uses explicit completion rather than frequent polling, keeping the mobile flow
simple and respecting the shared authentication limiter. All login operations use that limiter.
Responses carrying login material set no-store/no-cache/no-referrer headers. Audit entries
contain session/account IDs, never codes, browser secrets or raw Telegram messages.

Challenge expiry and locking use database time. Each new challenge opportunistically removes
at most 100 challenges that expired more than an hour ago. Idle deployments retain expired
rows until a later request; enforce a separate retention job for strict deletion deadlines.

## Deployment

- Apply migration 20261017_03 and grant application DML on telegram_login_challenges.
- Set TELEGRAM_FACTORY_USERNAME to the actual bot username without @.
- Set AUTH_TELEGRAM_ENABLED=true only with TELEGRAM_FACTORY_ENABLED=true, a verified token,
  a strong webhook secret and an HTTPS TELEGRAM_WEBHOOK_BASE_URL.
- Register and test the factory webhook on an origin reachable by Telegram. A Vercel preview
  protected by Vercel Authentication cannot receive Telegram delivery.
- Keep AUTH_DEV_BOOTSTRAP_ENABLED=false, RATE_LIMIT_ENABLED=true and session/security controls
  enabled. Production supports OIDC or this provider; neither is enabled implicitly.

The implementation and PostgreSQL tests do not establish live Telegram delivery. No factory
webhook is registered by this feature. Keep the provider disabled until deployment prerequisites
and a real browser → Telegram → browser sign-in are verified. Generated-bot execution remains
a separate deployment requirement.

If the final response is lost after consumption, restart sign-in. The raw session token is not
stored for replay. Refreshing the dashboard also requires a new login because the session
token is kept only in page memory.
