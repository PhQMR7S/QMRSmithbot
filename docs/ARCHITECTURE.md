# QMRSmithbot Architecture

## Product model

QMRSmithbot is a multi-tenant Telegram bot creation and runtime platform. A user owns one or more bot projects. Each project has a versioned workflow definition, configuration, integrations, and isolated runtime state.

## Layers

1. **Control plane** — users, identities, sessions, tenants, memberships, projects, plans, billing, templates, settings, publishing, audit logs.
2. **Builder** — visual workflow representation and validation.
3. **Runtime** — event ingestion, platform policy middleware, workflow execution, Telegram delivery.
4. **Async plane** — queues and workers for broadcasts, scheduled work, imports, and long-running tasks.
5. **Data plane** — PostgreSQL for durable state, Redis for ephemeral state/queues, object storage for assets.
6. **Observability** — structured logs, metrics, traces, health checks, and audit events.

## Authentication and tenant security

The control plane uses an explicit trust chain:

`User → Identity → Session/Token → Principal → Tenant → Membership/Role → Permission → Project`

- `users` is the internal account record.
- `identities` binds an authentication provider + immutable subject to a user.
- `sessions` stores only a SHA-256 hash of an opaque bearer token, with absolute expiry, idle expiry, and revocation.
- A request resolves to a `Principal(user_id, session_id)` before protected resources are reached.
- Tenant context is resolved from membership and, when necessary, `X-QMRSmith-Tenant-ID`.
- `AuthorizationService` applies deny-by-default role permissions.
- Project persistence filters by `tenant_id`, providing defense in depth against cross-tenant IDOR.
- Production authentication fails closed until a real identity-provider adapter is configured.

This layer is deliberately independent of Telegram Runtime. Telegram identity/provisioning can later become one authentication integration without becoming a shortcut around tenant authorization.

## Mandatory platform subscription gate

Hosted bots pass through a platform access middleware before user-defined workflow execution. The middleware can require membership in one or more configured Telegram channels. The requirement is controlled by the platform, not by an individual bot project, and is applied only to bots running on QMRSmithbot infrastructure. Admin bypass and emergency disablement are explicit platform policies and are audited.

## Security principles

- Bot tokens and credentials are secrets; never commit them to source control.
- Encrypt sensitive credentials at rest when persisted.
- Tenant isolation is enforced at the service/data layer.
- Validate Telegram webhook authenticity and request shape.
- Apply per-user, per-bot, and platform rate limits.
- Treat custom code and integrations as privileged capabilities with explicit limits.
- Every publish/configuration/security-sensitive mutation produces an audit event.

## Release model

Draft → Validate → Test → Publish → Observe → Rollback.

Published bot versions are immutable. A new change creates a new version. Rollback switches the active version pointer rather than mutating historical versions.

## Initial stack

- Python 3.12+
- FastAPI for service APIs
- aiogram 3.x for Telegram bot integration
- PostgreSQL
- Redis
- SQLAlchemy 2.x + Alembic
- Pydantic v2
- pytest
- Ruff
- Docker Compose for local development

The architecture is intentionally modular so the dashboard/frontend can evolve independently of the runtime engine.
