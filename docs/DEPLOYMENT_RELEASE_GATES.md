# Deployment architecture and release gates

## Current verified boundary

The factory is connected through an authenticated public ingress and a protected control plane.
Static text bots have a bounded request-time consumer; see INLINE_TEXT_RUNTIME.md for its
supported graph, setup, delivery semantics and validation limits. Advanced queue workflows
remain disabled until their persistent worker/action consumer passes its release gates.
The checklist below covers the broader platform, including features beyond text templates.

## Minimum topology

- **Vercel**: FastAPI control plane, dashboard, and authenticated incoming webhooks.
- **Dedicated PostgreSQL**: source of truth for projects, workflow versions, leases,
  idempotency, factory conversations, and update inbox. Never share another app's tables
  or deploy against an expiring free database as a production source of truth.
- **Shared authentication rate limiter**: PostgreSQL is supported after migration
  20261017_02 with RATE_LIMIT_BACKEND=postgresql; see POSTGRES_RATE_LIMITING.md.
  Alternatively use a dedicated Redis-compatible endpoint. Check support
  for atomic Lua EVAL and sorted-set commands; REST-only interfaces cannot be used
  directly as REDIS_URL with redis-py without an appropriate protocol adapter.
- **Durable consumer**: independently scheduled/hosted process or an authenticated,
  bounded queue invocation to consume the Telegram inbox and action ledger. A Vercel
  deployment does not continuously run TelegramRuntimeWorker.
- **Identity**: configured OIDC provider, server-side sessions, and an explicit
  Telegram-to-web-account linking flow. Never equate raw numeric Telegram IDs with
  internal platform identity IDs.
- **Credentials**: fresh BotFather tokens and strong independently generated encryption,
  webhook, and OIDC secrets in hosting environment variables; never commit them.

## Production readiness checklist

- [ ] Dedicated persistent PostgreSQL instance and backups configured
- [ ] All Alembic migrations applied and checked against the deployed revision
- [ ] Selected shared rate-limit backend is reachable and rejects excess attempts
- [ ] OIDC issuer, client, callback and session state secrets configured
- [ ] Worker consumer deployed and demonstrated to handle inbox *and* action ledger
- [ ] Queue retries, dead-letter behavior, restart recovery, and idempotency checked
- [ ] Tenant isolation, project permissions and webhook validation checked live
- [ ] Telegram end-to-end test: create draft → publish → bind bot → receive update →
      dispatch response → retry duplicate → stop/resume
- [ ] Factory bot token rotated if it was exposed, and HTTPS webhook installed only
      after the rest of the checks pass
- [ ] GitHub CI, preview smoke checks and deployment release gates succeed

## Avoid misleading healthy states

HTTP GET /health only establishes that a FastAPI function responded. Never treat it as
a worker, storage, or Telegram delivery readiness check. Keep each execution transport disabled until its own storage, authentication and consumer checks pass.

## Free plan constraints

Free web services can sleep or be suspended; free databases may expire and storage
or bandwidth caps apply. Any claimed 24/7 availability or unlimited bot count requires
actual capacity planning, quotas, measurements, and an appropriate hosting contract.
