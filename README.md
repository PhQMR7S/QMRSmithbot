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

The private Telegram factory is connected at @Manjerxbot. Factory chat supports encrypted bot-token binding, welcome/reply/command editing, previews, confirmed publication, stop/resume, and scoped statistics. The bounded text runtime returns static Telegram webhook replies without a persistent worker. Enable it only after applying migrations and deploying the authenticated child ingress.

Advanced workflow actions (HTTP, delays, branching, variables and action chains) still require the separate durable queue runtime. Its activation gate remains disabled. Telegram login is available when configured; existing OIDC identities remain separate until explicit account linking is implemented. There is no fixed project-count cap, but provider and execution limits still apply.

See `docs/INLINE_TEXT_RUNTIME.md` for runtime boundaries, setup and retry semantics.

Read `docs/DASHBOARD.md`, `docs/TEMPLATES.md`, `docs/PROJECT_MANAGEMENT.md`, `docs/TELEGRAM_FACTORY.md` and `docs/VERCEL_DEPLOYMENT.md` for functionality, prerequisites and validation limits.
