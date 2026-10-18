# Conversational form builder

The `form` template adds a real multi-step questionnaire to the existing inline runtime. The web studio edits questions and the native bot panel publishes the same workflow version. Text, bounded numbers and 2–8 choice buttons are supported. A choice may continue to the next question, jump to a later question, or finish. Backward/missing branches, duplicate question IDs, blank/duplicate choices and invalid numeric ranges are rejected. The current bounded implementation allows 1–20 questions, 1000-character visitor answers and 500-character prompts. This is not an arbitrary-code executor or a general-purpose condition-expression canvas.

## Draft and live behavior

Question configuration is a validated `Form` stored in workflow variables. Saving creates a draft with an expected-version check; it does not change the active bot. Publishing uses the existing verified-webhook activation path. Editing the welcome and form in the same web session advances their shared version without losing unsaved question edits. Conflicting remote edits retain local content and require reload/reconciliation.

`/start` displays the welcome and an explicit Start button. Each visitor has a separate project-scoped session containing an immutable snapshot of the questionnaire and its published version. New publications do not mix new questions with old answers. A nonce and the current question ID bind choice/skip/cancel callbacks to that visitor's current step. Verified choice navigation edits the bot's existing prompt instead of posting a new prompt for every button press. Optional questions can be skipped; required questions cannot. Numeric answers are finite and bounded, including adversarial decimal exponents. Attachments and token-shaped input are rejected by the text-form collector; contact bots retain their separate attachment routing.

Sessions expire after 30 minutes of inactivity. Expiry is checked and old partial data is removed when that visitor next interacts; this release does not promise scheduled deletion of untouched expired rows. `/cancel` discards a partial session; `/restart` explicitly discards it and returns to Start. A repeated `/start` preserves current progress. The existing project transaction lock and `(project_id, update_id)` cache prevent duplicate completed submissions from repeated webhook deliveries. Completion and progress commands are returned only after the transaction commits.

## Owner inbox

Completed responses store their original title, question prompts, answers and workflow version. Both the web inbox and native paginated viewer require the project owner, in addition to tenant/project permissions. Editors may change question drafts but cannot read or delete visitor submissions. Completed submissions can be downloaded as JSON in the browser or explicitly deleted after confirmation. Question changes do not rewrite historical answers. The native viewer shows one answer per page to stay within Telegram message limits. New submissions do not trigger unsolicited messages; the owner checks the inbox.

## Database rollout

Alembic `20261018_06` adds `bot_form_sessions` and `bot_form_submissions` with project foreign keys, lookup/expiry indexes and a project/time/ID inbox index. The deployed `qmrsmith_app` role also needs SELECT, INSERT, UPDATE and DELETE on both new tables. These deployment-specific grants are applied separately from the portable migration.

The rollout prepares the public gateway's form routes/assets first, temporarily makes readiness accept both adjacent additive-schema revisions, tests DDL and application-role access on an expiring isolated Neon branch, applies the migration/grants transactionally, and then deploys the feature with readiness requiring the new revision. No existing tables or user data are dropped.

## Verification

Unit tests cover form paths, unsupported variables, blank/ambiguous fields, Unicode numeric input, invalid/excessive numeric values and forged callback authors. The disposable PostgreSQL test covers publication, forward choice branches, frozen sessions across a new publication, invalid answers, old/foreign callback rejection, repeated completion delivery, owner-only inbox access, deletion, cancellation and expiry. Browser tests cover question editing/reordering, local previews, numeric validation, welcome/form version coordination, retained conflict text, JSON downloads, inbox deletion and mobile layout. Browser interaction tests use synthetic data; real private Telegram delivery is not automated.

References inform an independent implementation: visual/structured editing from telegram-ui-builder and telegram-bot-builder, multi-step state and submissions from HG-TeleFlare, and explicit owner-confirmed lifecycle boundaries from telegram-managed-bot-factory. No external project source code or assets were copied. No additional paid service, AI provider or n8n instance is enabled.
