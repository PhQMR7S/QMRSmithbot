# Authentication, Identity, Tenant Security

QMRSmithbot now has a dedicated security boundary between an external identity and tenant-scoped application resources.

## Request trust chain

```text
User
  ↓
Identity (provider + subject)
  ↓
Server-side Session
  ↓
Bearer Session Token
  ↓
Principal (user_id + session_id)
  ↓
Tenant Context
  ↓
Tenant Membership / Role
  ↓
Permission
  ↓
Tenant-scoped Project
```

## Identity

`users` remains the internal account record. `identities` maps an external authentication provider and immutable subject to exactly one user. The current development bootstrap uses `provider=development`; production must use a real authentication provider before enabling access.

## Sessions

Session tokens are opaque, cryptographically random values. Only a SHA-256 hash is persisted. Sessions have both an absolute expiration and an idle timeout and can be revoked server-side. Raw tokens are never written to the database.

The API accepts the token only through `Authorization: Bearer <token>`. Project endpoints do not accept the old user-ID header as an authentication mechanism.

## Development bootstrap

`POST /api/v1/auth/dev/session` exists only for development/test environments. It creates the development identity, personal tenant, and session in one transaction. It is explicitly disabled in production by configuration validation.

## Tenants

Every authenticated development user receives a personal tenant. A user can later belong to multiple tenants through `tenant_memberships` with one of four roles:

- `owner`
- `admin`
- `editor`
- `viewer`

When a user belongs to more than one tenant, requests must provide `X-QMRSmith-Tenant-ID`.

## Permissions

Authorization is deny-by-default and centralized in `AuthorizationService`:

| Role | Read | Write | Publish | Tenant management | Member management |
| --- | --- | --- | --- | --- | --- |
| Owner | ✓ | ✓ | ✓ | ✓ | ✓ |
| Admin | ✓ | ✓ | ✓ | ✓ | ✓ |
| Editor | ✓ | ✓ | ✓ | — | — |
| Viewer | ✓ | — | — | — | — |

The API checks the permission before invoking project operations. The project persistence layer also filters by `tenant_id`, providing a second resource-scope boundary against IDOR/cross-tenant access.

## Migration safety

Migration `0003_identity_tenant_security` creates the identity/session/tenant tables, creates personal tenants for existing users, backfills existing projects to those tenants, then makes `bot_projects.tenant_id` non-null. Existing audit records are backfilled with the corresponding tenant when a project link exists.

## Production gate

This phase intentionally does **not** pretend that a real production identity provider exists. Production authentication remains fail-closed until a real provider adapter is wired. Telegram Runtime is a separate later phase and is not used as a shortcut for dashboard authentication.
