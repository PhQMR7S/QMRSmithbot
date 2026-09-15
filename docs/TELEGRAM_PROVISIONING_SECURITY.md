# Telegram Bot Provisioning & Webhook Security

This phase establishes the credential boundary before Telegram Runtime. Runtime handlers are intentionally not implemented here.

## Provisioning

`POST /api/v1/projects/{project_id}/telegram/bot` requires authenticated tenant membership and `PROJECT_WRITE` permission. The submitted BotFather token is sent only to Telegram's `getMe` validation endpoint and is never written to logs or audit metadata.

After validation:

- the token is encrypted at rest with a dedicated Fernet key;
- only the last four token characters are retained separately for operator display;
- a monotonically increasing credential version tracks replacement;
- the Telegram bot ID is persisted on the tenant-scoped project;
- one Telegram bot cannot be assigned to multiple projects;
- the webhook secret is generated with the operating system CSPRNG;
- only the SHA-256 hash of the webhook secret is persisted;
- the plaintext webhook secret is returned only once from provisioning/rotation.

The encryption key must come from deployment secret management and must never be committed to source control.

## Webhook security

Telegram's `X-Telegram-Bot-Api-Secret-Token` header is verified against the stored hash using constant-time comparison. Missing, oversized, or incorrect secrets are rejected before any update processing.

The runtime phase must register the verifier as a mandatory dependency on every project webhook route. The URL must be HTTPS and project-scoped; no webhook endpoint may infer tenant context from untrusted request data.

Webhook secret rotation invalidates the previous secret immediately. Runtime deployment must update Telegram's webhook configuration atomically with the application rollout so there is no period where an old secret remains accepted.

## Token lifecycle

Provisioning replaces the encrypted token and rotates the webhook secret. Disconnect removes the credential record and clears Telegram identity fields from the project. Runtime must additionally call Telegram's webhook removal operation when a bot is disconnected or disabled.

The platform must never expose the decrypted bot token through API responses, logs, audit records, exception messages, metrics, traces, or client-side state.

## Boundary with Runtime

This phase deliberately does **not** start polling, dispatch workflows, or activate webhooks. The next runtime phase must add webhook registration/removal, Telegram API client lifecycle management, idempotent update handling, replay protection where required, bounded payload/resource handling, and graceful shutdown before production activation.
