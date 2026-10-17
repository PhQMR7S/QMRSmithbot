# QMRSmithbot

Production-oriented Telegram bot builder platform foundation.

## Architecture

The platform is designed as a multi-tenant control plane and runtime with:

- Authentication, identity, sessions, tenant isolation, roles, and permissions
- Visual workflow definitions and validation
- Versioned project lifecycle with publish/rollback
- Telegram bot provisioning and durable workflow runtime foundations
- Platform-level access policies
- Async queues/workers, observability, audit, and security controls

## Security boundary

The request path is intentionally layered:

`User → Identity → Session/Token → Principal → Tenant → Membership/Role → Permission → Project`

Production authentication fails closed until a real identity-provider adapter is explicitly configured. Development bootstrap sessions are unavailable in production.

## Development

```bash
pip install -e '.[dev]'
ruff check .
python -m compileall -q src tests migrations
alembic upgrade head --sql
pytest
```

Database migrations must be applied before starting application workers.

## Current status

Development branch capabilities now include:

- Arabic/English account preferences and a responsive same-origin `/dashboard`.
- Versioned starter templates for welcome, exact text replies and command responses.
- Tenant-scoped project search, rename, stop/resume and workflow draft/publish lifecycle.
- Opt-in private Telegram factory menus, persistent draft wizard and per-update deduplication.
- Vercel FastAPI entrypoint preparation.

These are development capabilities, not a deployed production factory. The dashboard requires a configured OIDC provider. The Telegram factory webhook requires PostgreSQL migrations, a factory bot token and a separate webhook secret. It is disabled by default. Factory Telegram identities are distinct from OIDC identities until explicit linking is implemented.

Generated-bot delivery still requires durable queue workers or a serverless queue adaptation. Advanced bot types, full platform administration and infrastructure deployment remain incomplete. There is no fixed project-count cap, but provider and execution limits still apply.

Read `docs/DASHBOARD.md`, `docs/TEMPLATES.md`, `docs/PROJECT_MANAGEMENT.md`, `docs/TELEGRAM_FACTORY.md` and `docs/VERCEL_DEPLOYMENT.md` for functionality, prerequisites and validation limits.
