# Optional Android/Termux QA (not production hosting)

Termux is useful for developer-side diagnostics, but is **not** the production bot worker.
Android battery optimizations, doze, connectivity changes, and process eviction prevent
any honest claim of uninterrupted 24/7 service.

## Read-only health probe

Run in Termux after installing curl:

```sh
pkg update
pkg install curl
curl --fail --silent --show-error --max-time 20 https://YOUR-QMRSMITHBOT-URL/health
```

A 200 response with `{"status":"ok","service":"QMRSmithbot"}` checks only
the HTTP app entrypoint. It does **not** prove queue execution, database connection,
Redis availability, Telegram callback processing, or the production release.

## Do not put credentials on the device

Do not paste bot tokens, OIDC client secrets, database URLs with credentials,
or encryption keys into shell history, Git, screenshots, or chat messages.
Use managed provider secret stores for production. Avoid exposing local ports to
the internet from a phone and never disable the webhook readiness gate to make a
test look successful.

## Real release prerequisites

See [DEPLOYMENT_RELEASE_GATES.md](DEPLOYMENT_RELEASE_GATES.md). In particular,
the Telegram durable inbox needs a designated persistent worker, a dedicated
PostgreSQL instance, a compatible Redis service, and an end-to-end Telegram
verification. Termux can optionally inspect a protected test environment but
should not be substituted for these dependencies.
