# Telegram Dispatcher

The dispatcher is the deterministic boundary between accepted Telegram updates and the future workflow runtime.

## Pipeline

`durable inbox → Update validation → event classification → published workflow selection → trigger resolution → immutable dispatch plan → workflow runtime`

The dispatcher never executes workflow nodes or Telegram API actions.

## Published-version invariant

Only the project's active version is eligible, and it must be marked published and the project must be `running`. The Telegram bot ID from the inbox must match the project binding. This prevents stale, unpublished, cross-bot, or stopped projects from receiving runtime execution.

The stored workflow is validated again at dispatch time. A corrupted published definition is treated as a terminal runtime configuration error rather than retried indefinitely.

## Event classification

The initial classifier supports:

- `trigger.command` for `/command` and `/command@this_bot`;
- `trigger.message` for text messages;
- `trigger.callback` for callback-query data;
- `unknown` for updates outside the initial trigger surface.

Commands are normalized to lowercase. A command explicitly addressed to another bot is not treated as a command for this bot.

## Trigger matching

Matching is deliberately bounded and deterministic:

- commands: `command` or `commands`;
- messages: exact `text`, `starts_with`, or `contains`;
- callbacks: exact `data` or `starts_with`.

Regex matching is intentionally not accepted at this boundary because user-authored regular expressions can create avoidable CPU/latency risks. A future regex feature must use a safe, bounded engine and explicit limits.

## Delivery semantics

The transport remains **at-least-once**. Dispatcher output is therefore a plan, not proof that execution happened exactly once. The future workflow runtime must use deterministic idempotency keys derived from the tenant, project, workflow version, update, and action identity before performing externally visible side effects.

## Ordering

PostgreSQL `SKIP LOCKED` provides safe concurrent consumption, not strict per-chat ordering. If a workflow requires conversational ordering, the future runtime must add an explicit per-conversation serialization policy rather than assuming queue order.

## Next boundary

The next phase implements workflow execution against `DispatchPlan`: graph traversal, conditions, data context, action handlers, Telegram API calls, idempotency, execution records, timeouts, retry classification, and observability. The webhook and dispatcher layers must remain free of workflow side effects.
