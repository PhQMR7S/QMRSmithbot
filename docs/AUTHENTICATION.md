# Authentication, Identity, Tenant Security

## Security chain

`User → Identity → Session/Token → Principal → Tenant → Membership/Role → Permission → Project`

### User

A `users` row is the durable application actor. Telegram identity and future dashboard identity providers map to this actor rather than being used directly as authorization context.

### Identity

`identities` stores an external provider plus immutable subject. The `(provider, subject)` pair is unique so one external identity cannot silently map to multiple users.

### Session / Token

Sessions use opaque, high-entropy bearer tokens. Only a SHA-256 token hash is persisted. Sessions have both absolute and idle expiration and support server-side revocation. Raw tokens are never logged or stored in database columns.

The development bootstrap endpoint creates a development identity/session only when `APP_ENV` is not `production` and `AUTH_DEV_BOOTSTRAP_ENABLED=true`. Production configuration rejects that flag and therefore cannot accidentally expose the bootstrap path.

A production identity-provider adapter remains an explicit integration boundary; there is no fallback from production authentication to a user-supplied header.

### Tenant

Every project belongs to exactly one tenant. Tenant membership is the authoritative relationship between an authenticated user and a tenant. A tenant context may be selected only when the authenticated user is a member of that tenant.

If a user belongs to multiple tenants, an omitted tenant context is rejected instead of guessing. This prevents accidental cross-workspace operations.

### Permissions

Roles are mapped to an explicit permission set:

- `owner`: all tenant permissions
- `admin`: project lifecycle + tenant/member management
- `editor`: project read/write/publish
- `viewer`: project read only

Authorization is deny-by-default. Project endpoints check the authenticated principal, tenant membership, permission, and project tenant scope before executing the operation.

## Data isolation

Project persistence queries use `tenant_id` rather than trusting a caller-provided owner ID. Service methods first establish tenant ownership of the project and then operate within that scope. A project outside the selected tenant is treated as not found.

The database also enforces the tenant foreign key and non-null project tenant scope.

## Audit boundary

Security-sensitive project lifecycle operations remain auditable. Audit records can reference actor, tenant, project, request ID, action, metadata, and detail. Request-ID propagation is the next security-control-plane increment so that every security-sensitive mutation can be correlated end-to-end.

## Hardening checklist

Before Telegram runtime is started, the platform must have:

1. Stable authentication/identity boundary.
2. Server-side session validation and revocation.
3. Tenant membership and explicit RBAC.
4. Tenant-scoped project persistence.
5. Negative cross-tenant authorization tests.
6. Request-ID/audit correlation.
7. Redis-backed rate limiting with fail-closed behavior for security-sensitive endpoints.
8. Explicit production identity-provider configuration.

Telegram provisioning/runtime is intentionally downstream of these controls.
