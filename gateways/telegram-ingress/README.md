# Telegram ingress

This service exposes health, secret-authenticated Telegram webhook routes, and a path-allowlisted authenticated dashboard proxy. See docs/VISUAL_STUDIO.md in the repository for the dashboard boundary. Telegram stores a normal
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
protected. The main application retains Vercel protection. Dashboard APIs require application sessions and tenant authorization; arbitrary routes, development authentication and credential APIs remain inaccessible. Telegram webhook routes reject all query parameters; dashboard routes accept only enumerated query fields. All routes bound payloads and reject unexpected upstream responses.
Upstream failures return a generic 503 so Telegram can retry.

This service does not run generated-bot queue consumers. It only delivers factory updates.
