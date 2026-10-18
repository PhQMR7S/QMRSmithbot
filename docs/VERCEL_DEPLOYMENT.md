# Vercel deployment preparation

The root app.py exports the existing FastAPI application using Vercel's supported entrypoint discovery. Python is pinned to 3.12. No long-running worker is started from the HTTP application.

## Deployment gate

This is deployment preparation only. Do not activate Telegram webhooks until durable processing has a deployed consumer. Current webhook handling persists to PostgreSQL, but TelegramRuntimeWorker is a continuous consumer; Vercel does not keep that process alive between HTTP invocations. A healthy /health response alone does not establish a functional bot.

Before production:
- Provision persistent PostgreSQL, apply all Alembic migrations and configure pooled connectivity.
- Configure Redis for the production rate limiter.
- Configure the existing OIDC provider and production session settings; do not disable authentication to get a build passing.
- Adapt inbox and action consumers to a bounded authenticated queue invocation with durable delivery and recovery, or run these workers on an independently managed runtime.
- Implement the factory chat menus and handlers; the factory token configuration alone does not create a Telegram factory UI.
- Store the factory token, credential encryption key and identity-provider secrets directly in Vercel environment secrets. Set administrator IDs as a JSON array. Never put credentials in source.
- Configure the final HTTPS webhook origin and validate secret checks, retries, duplicate handling and end-to-end delivery before webhook activation.

No real secrets are shipped. Root app discovery can be exercised locally with a TestClient; platform build, live PostgreSQL/Redis and Telegram delivery still require deployment validation. Do not use filesystem SQLite or in-memory state on Vercel. Do not replace durable queue processing with untracked background threads/tasks.

References:
- https://vercel.com/docs/frameworks/backend/fastapi
- https://vercel.com/docs/frameworks/backend
