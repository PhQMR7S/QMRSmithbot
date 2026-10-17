# Preview deployment status — 2026-10-17

Repository: PhQMR7S/QMRSmithbot. Branch: feat/account-language-preferences / PR #23.
Main is not merged. No Telegram webhook has been activated.

## Database and application role

The qmrsmithbot database uses the existing Neon project and shares its compute/quotas.
It has separate application tables from neondb. Migrations are applied through 20261017_02.
The application connects as qmrsmith_app, with an independently generated password and no
superuser, create-role, create-database, replication or neon_superuser membership.
It has application-table DML, sequence use, and read-only SELECT on alembic_version.
Credentials are stored only in encrypted Vercel Preview environment variables.

Committed insert/read/delete checks succeeded as the application role. Existing neondb tables
were not changed. Migration execution revealed historical revision identifiers too long for
Alembic's default 32-character field; the initial migration now widens the version field.

## Reliability changes

Factory update markers now include the configured factory bot ID. Previously the processor
omitted a required component of the primary key, which would fail against real PostgreSQL.
The PostgreSQL integration job verifies concurrent duplicate delivery, language persistence,
internal/Telegram identity separation and one-time draft creation with real constraints.

An optional PostgreSQL authentication limiter removes the requirement for a separate Redis
service for this control. It uses atomic fixed windows, database time, hashed keys, bounded
expiry cleanup and failure-closed behavior. Redis remains available as a separate backend.
Preview uses RATE_LIMIT_ENABLED=true and RATE_LIMIT_BACKEND=postgresql.

The /ready endpoint checks application tables and the expected schema revision with a
five-second query deadline. It returns generic 503 responses without connection details,
and no-store headers. /health remains a liveness check. The root path redirects to /dashboard.

## Verification

Preview commit 9a5ff30bda05beb2f3d671e0b002838f7d6a3f11:
https://qmrsmithbot-9dvlymasj-phqmr7s.vercel.app/dashboard

Verified /ready returns 200 from Vercel using the restricted application role.
An OIDC-start request reached the configured PostgreSQL rate limiter and persisted a counter;
the request then returned the expected provider-unavailable response because OIDC is not configured.
This is not a successful login.

PostgreSQL 18 CI passed migrations twice plus three integration scenarios, including 20
concurrent rate-limit checks and expired-window reset. The runtime-only packaging job passed.
The quality job exposed the expected-schema test needing the new security_rate_limits table;
the follow-up commit corrects that expected set. Record the final CI run result before release.

## Remaining release requirements

OIDC identity provider and account linking, factory credentials, public reachable webhook
origin, durable generated-bot consumers and advanced templates remain incomplete.
Factory and generated-bot activation gates remain disabled, deployment protection stays enabled,
and no paid plan was activated. A ready HTTP database probe does not establish Telegram delivery.

Before public release, verify production identity, durable inbox and action-ledger consumption,
retry recovery, actual Telegram delivery and the complete create/publish/bind/stop/resume flow.
