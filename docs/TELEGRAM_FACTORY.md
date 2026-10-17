# Telegram factory menus

POST /api/v1/factory/webhook is a dedicated, opt-in control-plane Telegram endpoint. It is separate from generated-bot runtime webhooks and runs its bounded menu/wizard work in the request, without a continuously running worker. It does not fix generated-bot queue delivery yet.

## Included
- Private /start and /start deep links, /help, /language, /cancel.
- Arabic/English selection saved to the mapped account.
- Inline home, template selection, paginated personal-workspace projects (8 per page, not a project-count cap), project state/details and confirmed stop/resume.
- Persistent creation wizard: template, name, welcome, optional keyword/command replies, review and one-time confirmation to create a workflow draft.
- Configured factory administrators see an informational admin entry. This is not a full platform administration panel and grants no cross-tenant permissions.

Incoming updates must carry the configured X-Telegram-Bot-Api-Secret-Token. Payloads are bounded and validated; groups, inline-only callbacks, mismatched private chat/user IDs and bot actors are ignored. Platform identities are resolved through provider=telegram plus the actual Telegram subject. External Telegram IDs are never equated with internal or OIDC user IDs. Existing web accounts are not automatically merged; explicit linking remains future work.

A per-actor PostgreSQL transaction advisory lock serializes conversation changes. A (factory bot ID, update ID) ledger deduplicates updates; marker, conversation and project draft commit in the same transaction before the webhook command response. The response uses Telegram's webhook API response mechanism. Callback acknowledgements are attempted separately after commit with a short timeout, and failure logs omit payloads/credentials.

One-time draft/action nonces prevent old confirmation buttons from confirming a newer wizard state. All project operations still use tenant permissions. Creation does not publish, bind credentials, activate a generated-bot webhook or start infrastructure. Token-like input is rejected from wizard fields to avoid persisting accidentally pasted credentials. Raw update payloads are not stored by this endpoint.

## Deployment prerequisites
1. Apply migrations through 20261017_01 to PostgreSQL.
2. Set TELEGRAM_FACTORY_ENABLED=true only after the configured factory token, encryption and production identity/platform requirements are met.
3. Set TELEGRAM_FACTORY_WEBHOOK_SECRET to a random 32–256 character URL-safe secret directly in hosting environment secrets. TELEGRAM_FACTORY_ADMIN_IDS is a JSON array of trusted numeric Telegram IDs.
4. Register https://YOUR_HOST/api/v1/factory/webhook with Bot API setWebhook using that same secret_token. Do not enable polling simultaneously. Start with max_connections=1 and allowed_updates=["message","callback_query"]. Do not log the token or request URL.
5. Test private start/language, all three creation wizards, cancellation, duplicate delivery, permission isolation and database failure before public activation.

## Limits and remaining work
No live Telegram webhook has been registered or tested by this change. PostgreSQL transaction, lock and migration behavior needs live integration validation. Unit and request tests use fake stores/sessions; they do not establish real delivery reliability.

Telegram does not return the result of API calls embedded in a webhook response. If the response is lost after the transaction commits, a retry is deduplicated and the user may need /start; this change does not provide a transactional outbound-delivery guarantee. It prevents duplicate project creation, not every possible lost/duplicate UI message. Add a durable outbox with receipt handling if stronger delivery guarantees are required.

The dedupe ledger currently requires retention/cleanup planning as it grows; do not prune entries while delivery retries could still occur. Stored conversations may contain user-authored welcome/reply content; establish a retention/deletion policy. Group management, attachments, payment, AI, advanced admin, bot-token linking, account linking and generated-bot worker adaptation are not implemented here. The existing production OIDC/Redis configuration remains required by the application.
