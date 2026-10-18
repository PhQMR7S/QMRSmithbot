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


## Native experience redesign

Application revision ce656c6262cd027f07adf31469cd9cd0f0d92162 adds in-place callback
navigation, native button styles, cards/compact library layouts, name search, status filters,
saved appearance settings, guided trigger/response creation, individual reply CRUD with
stale-version rejection, and a visitor response simulator. Opt-in RTL rich messages are
available, with /plain recovery and /appearance shortcuts. The public ingress accepts the
corresponding sendMessage/editMessageText/sendRichMessage responses; protection is unchanged.

Validation: 256 local tests passed, and CI run 39031494772 passed all four jobs including ten
real PostgreSQL scenarios and desktop/mobile browser checks. Live /ready returned 200;
ingress rejected an unauthenticated update with 401 and forwarded an authenticated ignored
update with 204. These HTTP checks do not establish actual Telegram rendering of rich
messages. See NATIVE_FACTORY_EXPERIENCE.md for precise scope.

This is a native chat redesign. A fully designed Mini App and universal support for every
Telegram feature are not implemented. Child-bot real Telegram delivery remains unverified.


## Buttons/files and contact products — 2026-10-18

The factory now offers buttons and contact as first-class templates. Button projects have
nested sections, text, HTTPS links and child-bot-scoped file uploads, with draft/live
publication. Contact projects copy visitor messages to their verified owner and route only
mapped owner replies back to that visitor, including supported attachments and block/unblock.
There is no fixed button/file-count quota; Telegram and hosting capacity limits still apply.
The owner must start the child bot before receiving contact messages. See BUTTONS_AND_CONTACT.md.

Migration 20261017_05 was tested on an isolated expiring Neon branch, then applied to the active
database with restricted app-role DML grants. Main app code 480a7555fac1ecd94d8443125ebb7ca913a34718
and the ingress production deployment were verified READY; CI run 39032690792 passed all four
jobs including twelve PostgreSQL integration scenarios. Real child-bot delivery remains
unverified: the test Bot API was mocked and no real separate child token was available.

The response path no longer serializes a five-second callback acknowledgement ahead of menu
processing. A 600 ms acknowledgement deadline runs concurrently, and conversation/permission
reads are cached only for the current request. A further performance change reuses bounded
upstream connections on lifespan-capable ASGI hosts (fallback is request-scoped) and exposes
Server-Timing for application/upstream measurement. Latest local validation: 265 tests passed;
final CI and deployment checks are linked on PR #23. Live readiness/authentication probes
returned 200/401/204, but those are not real Telegram end-to-end latency measurements. Free-host
cold starts and network latency remain possible; no fixed speed percentage is claimed.
