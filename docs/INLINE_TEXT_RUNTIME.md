# Factory text bots

The factory panel supports connecting a separate BotFather token, updating the project name,
previewing the latest draft, editing its welcome message or replacing its reply/command list,
and confirming publication. Draft changes do not affect the active version until publication.
Stop/resume uses the existing tenant-scoped project lifecycle. Statistics reflect persisted
project status; they are not delivery or audience analytics.

## Deployment

Apply migration 20261017_04 and grant application DML on telegram_inline_bots and
telegram_inline_updates. Deploy gateways/telegram-ingress with its existing private-origin,
server-only bypass header and factory webhook secret. Child route /bots/{project_id} derives
a separate HMAC secret for each project; the factory route and other projects cannot reuse it.
Enable TELEGRAM_INLINE_RUNTIME_ENABLED and set TELEGRAM_INGRESS_BASE_URL to the public HTTPS
ingress origin. The main API remains protected. No bot token or database credentials enter
the ingress service. Rotating the root secret requires re-publishing every connected child.

Token binding verifies getMe, rejects the factory token and cross-project bot assignments,
and encrypts the token using the existing Fernet key. Conversation state never stores it.
The API attempts to delete token-containing private messages after processing; Telegram
may reject deletion. A replacement token must belong to the same bot identity.

Publication accepts only a schema-v1 workflow with no variables: each command/exact-message
trigger connects to one static text action, with no conditions or outgoing action edges.
Every node must participate, commands are unique and /start is required. Telegram webhook
registration is verified before the database activation transaction commits. Failure rolls
back publication. A network failure after Telegram accepts the webhook can still leave its
registration changed; retry publication to reconcile. Incomplete activation returns 503.

## Delivery semantics

Private messages only. Plain text only, at most 3000 characters per reply. Unknown messages
receive no reply. Published content is selected under the project lock. Stopped projects
acknowledge updates without replying. Each accepted running-bot update stores its response
(including no-response decisions) keyed by project and Telegram update ID; raw incoming
messages are not retained in this cache. Duplicate requests replay the cached command.
This prevents duplicate workflow evaluation but does not guarantee exactly-once message
arrival: Telegram retries may produce duplicate replies, and webhook response delivery
cannot be acknowledged independently. No external action is executed by this transport.
The reply cache currently has no automatic retention job; capacity must be monitored.

The advanced queue consumer gate stays disabled. Do not infer support for HTTP, delayed jobs,
branching or arbitrary workflows from a successful text-bot publication.

## Validation

Unit tests cover supported templates, unsupported graph rejection, and per-project ingress
secrets. The PostgreSQL integration scenario exercises chat creation, encrypted binding,
publishing, duplicate replies, unpublished draft isolation, republishing, stop/resume,
authenticated HTTP replies and activation failure rollback. Telegram API calls in that
scenario are mocked. A real child token and real chat are needed to verify Telegram delivery.
