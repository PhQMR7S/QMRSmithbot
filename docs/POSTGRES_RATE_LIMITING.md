# PostgreSQL authentication rate limiting

Set RATE_LIMIT_ENABLED=true and RATE_LIMIT_BACKEND=postgresql after applying migration
20261017_02. Redis remains the default backend and is selected with RATE_LIMIT_BACKEND=redis.
Both reject authentication attempts with HTTP 503 if their configured backend is unavailable;
there is no silent fallback to per-process memory or an unprotected login.

The PostgreSQL backend uses an atomic upsert and database time to enforce fixed windows
starting at the first accepted request. Concurrent application instances share the same
counter. Denied attempts do not increment it. A new window resets the counter. This is a
fixed-window algorithm, distinct from Redis's sliding window: traffic around a boundary can
reach twice the configured count across two adjacent windows.

Keys are SHA-256 digests of the authentication rate-limit key; raw source IP addresses are
not stored in this table. Expiry is indexed. Each check removes at most 100 rows that expired
over an hour ago, skipping locked rows. Cleanup is opportunistic; idle deployments keep old
rows until traffic resumes. Use a separate retention job if a strict deletion deadline is needed.

Give the application role SELECT/INSERT/UPDATE/DELETE on security_rate_limits. It does not
need schema creation, table ownership, elevated Neon roles or migration privileges.
The readiness endpoint also needs read-only SELECT on alembic_version to check the deployed
schema revision. Never grant the application permission to update that version table.

Each PostgreSQL check has a five-second deadline and two SQL statements in one transaction.
This avoids a separate Redis service for small deployments, but consumes shared database
capacity. For higher authentication volume, choose Redis and capacity-test the deployment.
HTTP 429 includes Retry-After. Limits do not impose a maximum number of projects or bots.
