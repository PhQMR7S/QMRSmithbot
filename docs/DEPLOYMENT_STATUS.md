# Deployment status — 2026-10-17

Repository: PhQMR7S/QMRSmithbot. Development remains on feat/account-language-preferences /
PR #23; main is not merged. No paid plan was activated.

## Factory connection is active

Verified bot: @Manjerxbot (Telegram bot ID 7017004595), branded QMRSmithbot | مصنع البوتات.
Telegram accepted the factory webhook and getWebhookInfo confirmed the exact URL, zero pending
updates, no delivery error, max_connections=1 and allowed_updates=[message, callback_query].
Arabic/default and English commands plus profile descriptions were configured.

Public webhook: https://qmrsmithbot-ingress.vercel.app/webhook
The URL has no credentials or query parameters. Telegram must send its configured
X-Telegram-Bot-Api-Secret-Token header.

A direct Vercel-bypass key in Telegram's webhook URL was rejected by automatic approval review.
That route was not used. A separate minimal ingress service now verifies the Telegram secret
and forwards to the private factory with the Vercel key only in a server-side HTTP header.
No bot token or database credentials are in the ingress service.

Ingress project qmrsmithbot-ingress has public production endpoints /health and /webhook only;
preview deployments retain Vercel Authentication. The main qmrsmithbot project retains its
original all_except_custom_domains Vercel Authentication, dashboard authentication and tenant
permissions. The factory is deployed with APP_ENV=production, Telegram sign-in enabled,
development session bootstrap disabled, PostgreSQL authentication limits enabled and the
generated-bot consumer activation gate disabled.

All secrets are stored in encrypted hosting environment variables. No credentials are in Git.

## Verified live HTTP behavior

- Main /ready returned 200, and auth/methods reported Telegram enabled and OIDC disabled.
- Wrong factory webhook secret returned 401; a valid ignored update returned 204.
- Public ingress rejected the wrong secret (401) and forwarded a valid ignored update (204).
- A synthetic private /start update through the public ingress reached PostgreSQL and returned
  the correct Arabic sendMessage command with inline menu buttons. Redelivery returned 204.
  The synthetic account, its workspace and the exact update marker were then deleted.
  This HTTP probe did not send a Telegram chat message.
- Real deployment login challenge test: start 200, pending finish 202, wrong browser secret 401,
  cancellation 204, replay 401. The deep link correctly targeted @Manjerxbot.

A human must open @Manjerxbot and send /start to verify real chat delivery and interaction.
No actual user message or human browser → Telegram → browser sign-in has yet been observed.

## Storage and tests

Database qmrsmithbot has separate application tables within the existing Neon project; compute
and quotas are shared. Migrations are applied through 20261017_03. The application role has
application-table DML and read-only migration version access, without elevated role membership.

238 local tests passed. CI run 39027749161 passed quality, runtime-only packaging, eight real
PostgreSQL integration scenarios and desktop/mobile browser tests. Browser API data was mocked;
PostgreSQL tests and the live HTTP probes above cover different boundaries.

## Still incomplete

The connected factory creates and manages drafts. Generated-bot token binding from its chat
wizard, durable generated-bot inbox/action consumers, advanced templates, full platform admin
and linking pre-existing OIDC accounts remain incomplete. Generated-bot webhook activation
stays gated until its consumer is deployed and verified. A connected factory is not evidence
that all generated bot types can run.
