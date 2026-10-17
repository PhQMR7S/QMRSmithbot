# Telegram ingress

This small service exposes only GET /health and POST /webhook. Telegram stores a normal
webhook URL without any Vercel credential. Requests must carry the factory's strong
X-Telegram-Bot-Api-Secret-Token before any payload is forwarded.

The service forwards to the fixed, private FACTORY_ORIGIN over HTTPS. The Vercel protection
credential is attached only as an outbound server-side header. It never enters Telegram's
webhook URL, response JSON or user-visible links. Redirect following and environment proxy
discovery are disabled. No database or bot token is stored in this service.

Required server environment secrets:
- TELEGRAM_FACTORY_WEBHOOK_SECRET (same as the private factory)
- FACTORY_PROTECTION_BYPASS (Vercel automation key for the private factory project)
- FACTORY_ORIGIN (HTTPS Vercel origin, without a path or query)

Deploy this directory as a separate FastAPI project. Its production /webhook endpoint must
be publicly reachable while enforcing the Telegram secret; preview deployments can remain
protected. Do not broaden access to the main dashboard or its API. The ingress rejects all
query parameters, invalid payloads, excessive body sizes and unexpected upstream responses.
Upstream failures return a generic 503 so Telegram can retry.

This service does not run generated-bot queue consumers. It only delivers factory updates.
