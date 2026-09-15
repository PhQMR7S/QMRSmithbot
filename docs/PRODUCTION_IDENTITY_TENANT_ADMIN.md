# Production Identity & Tenant Administration

This layer is the mandatory security boundary before Telegram Bot Provisioning and Telegram Runtime.

## Authentication

Production authentication uses a provider-agnostic OpenID Connect Authorization Code flow with:

- HTTPS-only issuer and redirect URI.
- OIDC discovery with issuer verification.
- Authorization Code + PKCE S256.
- Cryptographically random `state`, `nonce`, and PKCE verifier.
- Server-side, short-lived OIDC transaction state.
- Encrypted PKCE verifier at rest.
- ID-token signature, issuer, audience, expiration, issued-at, nonce, and authorized-party validation.
- External identity keyed by immutable `(provider, subject)` rather than email.
- Email is used for verified invitation matching only; it never silently merges two accounts.

Required production settings:

```text
AUTH_DEV_BOOTSTRAP_ENABLED=false
AUTH_OIDC_ENABLED=true
AUTH_OIDC_ISSUER=https://...
AUTH_OIDC_CLIENT_ID=...
AUTH_OIDC_CLIENT_SECRET=...
AUTH_OIDC_REDIRECT_URI=https://.../api/v1/auth/oidc/callback
AUTH_STATE_ENCRYPTION_KEY=<Fernet key>
RATE_LIMIT_ENABLED=true
```

Generate the Fernet key with a trusted secret-management workflow. Never commit it to Git.

## Identity linking

`POST /api/v1/auth/oidc/link/start` starts a provider-link transaction for the authenticated user.
The callback never reassigns an existing external identity to another user. A conflict is rejected and audited.

## Tenant administration

A user can belong to multiple tenants. Tenant context is explicit through `X-QMRSmith-Tenant-ID` when an endpoint operates on a tenant.

Supported operations:

- list accessible tenants
- create tenant
- list members
- invite members
- accept invitations
- revoke invitations
- change member roles
- transfer ownership
- remove members

The owner role cannot be assigned through invitations or ordinary role changes. Ownership has a dedicated transfer operation so a tenant cannot be left without an owner.

Privilege changes revoke the affected user's active sessions, forcing a fresh authentication boundary after privilege changes.

## Invitations

Invitation tokens are random, single-use credentials. Only the SHA-256 token hash is stored. Invitations expire after seven days and require a verified OIDC email identity matching the invitation address.

Active invitations are protected by a PostgreSQL partial unique index, preventing duplicate active invitations for the same tenant and email.

## Authorization

Permissions are server-side and tenant-scoped. The role hierarchy is:

`OWNER > ADMIN > EDITOR > VIEWER`

Administrative operations enforce strict privilege ordering so an administrator cannot grant or mutate an equal-or-higher privilege role.

## Sessions

Sessions use random bearer tokens with only their SHA-256 hashes persisted. They have both absolute and idle expiration, explicit revocation, remote session revocation, and revoke-all-other-sessions support.

Sensitive privilege changes revoke affected sessions. Authentication failures are logged without persisting attacker-controlled request data into the audit database when no authenticated principal exists.

## Audit and correlation

Security-sensitive actions include request correlation and tenant context where available:

- authentication success/failure
- OIDC identity-link conflicts
- session creation/revocation
- authorization denial
- tenant creation
- invitation create/accept/revoke
- role changes
- ownership transfer
- member removal
- project lifecycle operations

`X-Request-ID` is generated or validated at the HTTP boundary and propagated into audit events.

## Production boundary

The development session bootstrap is forbidden in production. Production startup fails closed unless the real OIDC configuration and rate limiting are enabled.

This layer must remain green in static analysis, compilation, migration SQL generation, and tests before Telegram Bot Provisioning is started.
