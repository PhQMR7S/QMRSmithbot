# Preview deployment status — 2026-10-17

Repository: PhQMR7S/QMRSmithbot. Branch: feat/account-language-preferences / PR #23.
Main remains unmerged. No Telegram webhook has been activated and no paid plan was enabled.

## Database

Database qmrsmithbot is separate from neondb application tables but shares the existing Neon
project's compute and quotas. Migrations are applied through 20261017_03.
The application uses qmrsmith_app with independently generated credentials and no elevated
Neon/PostgreSQL role membership. It has application-table DML, sequence use and read-only
SELECT on alembic_version; it cannot change the migration version.

## Implemented and verified

- Factory update deduplication includes the factory bot ID and commits atomically with menu
  state and draft creation. Real PostgreSQL tests cover concurrent duplicate updates.
- PostgreSQL authentication rate limiting is enabled in Preview, with atomic shared fixed
  windows, hashed keys, bounded cleanup and failure-closed behavior. Redis remains optional.
- /ready verifies application schema, permissions and expected revision; /health is liveness.
- Optional browser-bound Telegram login now shares the factory's Telegram identity and
  workspace. It uses a five-minute challenge, a code absent from the deep link, a separate
  browser secret, a five-attempt lock, explicit bot confirmation, one-time session issuance
  and server-side cancellation. Raw codes/secrets/session tokens are not persisted.
- The dashboard discovers enabled providers and provides Telegram start/pending/cancel/finish
  states. Login and session secrets remain in page memory. Arabic/English and desktop/mobile
  flows are supported. Neither sign-in provider is enabled until its deployment is configured.

Verified deployment of commit 66b0bb539ac0c2b9d9eb6f14b13c1c7897348381:
https://qmrsmithbot-db359beyy-phqmr7s.vercel.app/dashboard

Its /ready endpoint returned 200, and /api/v1/auth/methods correctly reported both providers
disabled. This is not a successful real Telegram sign-in.

CI run 39026769267 passed quality, runtime-only packaging and all seven PostgreSQL integration
scenarios. These include concurrency, expiry, cancellation, wrong-browser/other-actor rejection,
five failed codes and a correct fifth code. 232 local tests passed (seven PostgreSQL cases
are opt-in locally and passed in CI).

Playwright with locally launched Chromium tested desktop 1366x900 and mobile 390x844:
login code display, pending status, server-cancel request, finish, logout, memory-only secrets,
no horizontal overflow and no JavaScript errors. The existing management browser flow also
passed. Browser API responses were mocked; this does not establish Telegram transport.
Screenshots were visually reviewed. Browser plugin was unavailable. A new browser CI job runs
both flows and retains QA screenshots as GitHub artifacts.

## Release requirements still open

Configure and verify the factory token, actual bot username, encryption/webhook secrets and a
public HTTPS origin reachable by Telegram. Vercel preview authentication currently blocks
Telegram transport; deployment protection has not been disabled.
Keep AUTH_TELEGRAM_ENABLED=false and TELEGRAM_FACTORY_ENABLED=false until real delivery is
tested. Production may use configured OIDC or the explicitly configured Telegram provider;
development bootstrap stays disabled and shared authentication rate limiting stays enabled.

Generated-bot durable inbox and action-ledger consumers, public activation, account linking
between pre-existing OIDC and Telegram identities, advanced templates and full platform admin
remain incomplete. Complete and validate the real create/publish/bind/deliver/retry/stop/resume
flow before describing the factory as production-ready.
