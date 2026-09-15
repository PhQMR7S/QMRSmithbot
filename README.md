# QMRSmithbot

Production-oriented Telegram bot builder platform foundation.

## Architecture

The platform is designed as a multi-tenant control plane and runtime with:

- Authentication, identity, sessions, tenant isolation, roles, and permissions
- Visual workflow definitions and validation
- Versioned project lifecycle with publish/rollback
- Telegram bot provisioning and runtime (next phase)
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

The authentication/identity/tenant security foundation is implemented and is being hardened before Telegram runtime work begins.
