# Workflow Runtime

The runtime consumes an immutable `DispatchPlan` and never selects a draft workflow. The execution boundary is deliberately split into:

`DispatchPlan -> ExecutionContext -> bounded graph traversal -> condition evaluation -> action handlers -> durable execution ledger`

## Safety properties

- Tenant and project identity come from the dispatch plan, never from node configuration.
- Only the published workflow version selected by the dispatcher can execute.
- Graph traversal is bounded by a step budget.
- Conditions use a small allow-listed grammar (`exists:key`, `equals:key=value`) rather than evaluating Python or arbitrary expressions.
- Unknown action types fail closed.
- Execution identity is `(project_id, update_id, workflow_version_id)` and is backed by a database uniqueness constraint.
- Side-effecting actions must be idempotent; the ledger prevents duplicate execution attempts from being treated as a new logical event.
- The execution ledger stores trace identity and node progress, enabling later observability and replay tooling without storing bot tokens.

## Deliberate production constraints

The runtime does not execute arbitrary user code, shell commands, Python expressions, or unrestricted regular expressions. External HTTP and Telegram actions are adapters with explicit timeouts and retry classification.

Strict per-chat ordering is a policy concern above the generic queue. When a workflow requires conversational ordering, the scheduler must serialize executions by `(project_id, chat_id)` rather than relying on `SKIP LOCKED` alone.

The next hardening layer is the action subsystem: idempotency-aware Telegram actions, bounded HTTP egress, delay scheduling, data persistence, cancellation, dead-letter/replay, metrics, and distributed tracing.
