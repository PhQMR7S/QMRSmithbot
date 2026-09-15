# Security Control Plane

This phase hardens the boundary before Telegram provisioning/runtime.

## Request correlation

Every HTTP request receives a server-generated UUID request ID. A caller-supplied `X-Request-ID` is accepted only when it parses as a UUID; otherwise it is replaced. The ID is exposed on the response and attached to the request context. Security-sensitive audit records use the same correlation ID.

## Audit correlation

Project publish/rollback events now persist:

- actor user
- tenant
- project
- action
- request ID

This makes tenant-scoped mutations traceable without storing bearer tokens or other authentication secrets.

## Authentication throttling

A Redis-backed sliding-window limiter protects authentication entry points. It is not a best-effort optimization:

- production requires `RATE_LIMIT_ENABLED=true`;
- Redis failure returns `503` instead of silently disabling the control;
- excessive authentication requests return `429`;
- the limiter uses a Redis sorted-set sliding window rather than a fixed-window counter, avoiding boundary bursts.

The first implementation applies the coarse per-IP bucket to the development bootstrap endpoint. The future production identity-provider adapter must add an independent identity/account bucket so distributed attempts against one account cannot bypass the IP bucket.

## Production defaults

Production fails closed when the security prerequisites are absent:

- Telegram factory token is required.
- Explicit non-default database configuration is required.
- Development authentication bootstrap is forbidden.
- Authentication rate limiting is required.

The real production identity provider is still an explicit integration boundary and is not replaced by a user-supplied identity header.

## Review basis

The controls follow the security principles of server-side session lifecycle management, fail-safe authorization, auditability, and layered rate limiting described by OWASP's authentication, session-management, authorization, logging, and anti-automation guidance.
