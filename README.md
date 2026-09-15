# QMRSmithbot

> A modern, extensible Telegram Bot Builder platform — No-Code, Low-Code, and Developer workflows.

## Vision

QMRSmithbot is being built as a production-grade platform for creating, deploying, developing, testing, and operating Telegram bots from a single system.

## Core principles

- Clean, modular architecture
- Security-first bot provisioning and secret handling
- No-Code + Low-Code + Custom Code paths
- Visual workflow engine
- Reusable templates and components
- Versioning, testing, publishing, and rollback
- Multi-tenant isolation
- Platform-level access protection
- Internationalization (Arabic/English first)
- Observable, scalable runtime

## Planned platform modules

- Bot Builder Dashboard
- Telegram management bot
- Bot provisioning and runtime
- Visual workflow engine
- Template engine
- Database builder
- API and webhook integrations
- AI-assisted bot construction
- Payments and subscriptions
- Analytics and audit logs
- Queue/workers
- Admin control center
- Mandatory platform-channel subscription gate for hosted bots
- CI/CD, automated testing, monitoring, and release management

## Current security foundation

The control plane now follows the explicit security chain:

`User → Identity → Session/Token → Principal → Tenant → Membership/Role → Permission → Project`

Implemented foundations include server-side opaque sessions with hashed tokens, absolute and idle session expiry, server-side revocation, tenant-scoped project persistence, deny-by-default role permissions, and development-only authentication bootstrap. Production authentication remains fail-closed until a real identity-provider adapter is wired.

See `docs/AUTHENTICATION.md` for the security model and migration details.

## Status

Foundation phase is active. Control Plane + Project Lifecycle and the Authentication + Identity + Tenant Security foundation are implemented. Telegram Runtime is intentionally not started until the security boundary is stable and green in CI.
