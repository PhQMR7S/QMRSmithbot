# Telegram Runtime Transport

This phase establishes the transport boundary only. Workflow dispatch and execution remain intentionally outside the webhook request path.

## Flow

`Telegram → HTTPS webhook → secret verification → bounded body read → Update validation → PostgreSQL atomic dedup → durable inbox → 2xx`

A future worker will consume the durable inbox and invoke the workflow runtime. The webhook handler never executes workflow logic.

## Webhook registration

- The webhook URL is generated server-side from the configured HTTPS base URL and project UUID.
- The bot token is decrypted only inside the Telegram API client context and is never returned or logged.
- `setWebhook` uses Telegram's secret-token header, explicit bounded client timeout, `allowed_updates=[]`, and `drop_pending_updates=false` so activation does not intentionally discard queued updates.
- Registration is verified with `getWebhookInfo` before the database transaction is allowed to complete.
- Disconnect first removes and verifies the remote webhook, then removes local credentials.

## Verification and replay protection

- `X-Telegram-Bot-Api-Secret-Token` is required and compared against a stored SHA-256 digest using constant-time comparison.
- The webhook path contains only a project UUID; the bot token is never placed in a URL.
- Request bodies are bounded to 1 MiB, including chunked requests without a trustworthy `Content-Length`.
- Telegram updates are validated through aiogram's typed `Update` model.
- `(project_id, update_id)` is protected by a database unique constraint and inserted with PostgreSQL `ON CONFLICT DO NOTHING`. Concurrent duplicates therefore collapse to one durable inbox row.

## Queue boundary

The inbox is a PostgreSQL-backed durable boundary rather than an in-memory queue. This prevents accepted updates from disappearing when an API process restarts. The worker/dispatcher is intentionally deferred until the transport contract is proven.

## Lifecycle and shutdown

Telegram API sessions are scoped to an operation and always closed in a `finally` block. The application lifespan also disposes the SQLAlchemy connection pool and the Redis rate-limiter resources during shutdown.

## Secret rotation rule

The existing generic webhook-secret rotation endpoint is not synchronized with Telegram's remote webhook configuration. Before enabling arbitrary rotation for an active webhook, a coordinated dual-secret or remote-first rotation protocol must be implemented. Until that protocol exists, runtime activation generates and installs the active secret itself, and webhook activation/deactivation are the supported lifecycle operations.

## Security invariants

- Never log bot tokens, decrypted credentials, webhook secrets, or session tokens.
- Never execute workflows synchronously inside the webhook handler.
- Never accept a client-supplied webhook URL.
- Never use Telegram bot tokens in URL paths.
- Do not treat Telegram source IPs as the primary authentication mechanism; the secret-token header is the application-level control.
