# Preview deployment status — 2026-10-17

Project: qmrsmithbot (Vercel), repository PhQMR7S/QMRSmithbot.
Development: feat/account-language-preferences / PR #23. Main remains unmerged.

## Database

Created database qmrsmithbot on the existing Neon project's main branch. This is a separate database sharing compute and project quotas with the existing resource; it is not a separate Neon project. Existing neondb application tables were not changed.

Applied the complete migration chain through 20261017_01 in one transaction.
A real PostgreSQL run exposed historical revision IDs longer than Alembic's default VARCHAR(32). The initial migration now widens the version column to 128 characters before applying the chain. The failed attempt rolled back completely.

Created qmrsmith_app with an independently generated password, without superuser, create-role, create-database, replication, or neon_superuser membership. Granted database CONNECT, schema USAGE, application-table SELECT/INSERT/UPDATE/DELETE and sequence USAGE/SELECT. No grants to the migration-version table. Public database CONNECT/TEMP privileges were revoked on qmrsmithbot only. Future application tables require explicit grants.
The pre-existing qmrsmith_owner role owns the database and is not used by the application; Neon automatically gives API-created roles elevated memberships.

Verified committed insert and read across separate calls as qmrsmith_app, then removed the exact synthetic verification record. Verified the role has no elevated membership.
Stored the application DATABASE_URL as an encrypted Preview environment variable in Vercel. No credentials are stored in repository files.

## Deployment and checks

Redeployed commit 08e601e9e7af8de68a3b125f0acbbd3abb8f9451:
https://qmrsmithbot-dro1yqb8e-phqmr7s.vercel.app/dashboard

GET /health returned HTTP 200 on this deployment. This endpoint does not query the database, so it is not proof of database connectivity from the deployed process.
A connector fetch of /api/v1/projects was blocked by deployment authentication; this result does not establish the application's authentication response.

211 local tests passed; Ruff and compile checks passed. Added a PostgreSQL 18 CI job applying all migrations twice to cover actual database execution. This new remote CI job has not yet been observed running.

## Remaining work

Preview continues to use staging settings with development-session bootstrap and the Telegram factory disabled. Vercel deployment protection remains enabled.
Factory credentials, production identity provider, production rate limiting, generated-bot durable queue consumers and advanced templates remain incomplete. No Telegram webhook was activated.
Next: configure identity and production-compatible rate limiting, verify database access from the deployment, then finish and validate durable message consumers and factory secrets before activation.
