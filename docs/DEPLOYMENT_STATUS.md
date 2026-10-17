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

Ingress project qmrsmithbot-ingress exposes /health, /webhook and authenticated /bots/{project_id};
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

The user confirmed that the factory responds in Telegram. A real child-bot chat and a full
human browser → Telegram → browser sign-in have not been observed.

## Storage and tests

Database qmrsmithbot has separate application tables within the existing Neon project; compute
and quotas are shared. Migrations are applied through 20261017_04. The application role has
application-table DML and read-only migration version access, without elevated role membership.

249 local tests passed. CI run 39030176753 passed quality, runtime-only packaging, nine
PostgreSQL integration scenarios and desktop/mobile browser tests. The new scenario covers
creation, encryption, confirmed publication, cached replies, draft isolation, republishing,
stop/resume, authenticated HTTP replies and activation failure rollback. Telegram API calls
in this scenario are mocked; it does not establish actual child-bot Telegram delivery.

## Text bot upgrade

Code fe2e9d37be5d9444a4cdc543b47193d903e0580b is deployed to the protected factory and the
public ingress. TELEGRAM_INLINE_RUNTIME_ENABLED is enabled; TELEGRAM_INGRESS_BASE_URL points
to the ingress. Factory panels support binding a separate BotFather token, previews, welcome
and reply/command editing, rename, confirmed publication, stop/resume and status statistics.
Tokens are encrypted and token messages receive a best-effort deletion attempt.
See INLINE_TEXT_RUNTIME.md for boundaries and retry semantics.

## Still incomplete

Advanced inbox/action queue consumers, HTTP/delayed/branching workflows, advanced templates,
full platform admin and linking pre-existing OIDC accounts remain incomplete. The advanced
consumer activation gate stays disabled. No real child token was available for a Telegram
end-to-end chat; connect one through its factory panel to perform that final validation.
