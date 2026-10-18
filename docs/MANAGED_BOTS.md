# Native Telegram creation

The connection panel offers “Create in Telegram” for an unbound project owned by the caller. The factory checks `getMe.can_manage_bots` before exposing the native creation link. If disabled, the panel explains the BotFather prerequisite and retains the token connection path.

Enable **Bot Management Mode** for `@Manjerxbot` in BotFather's Mini App. This account setting cannot be enabled through the Bot API. The factory webhook must include `managed_bot` in allowed_updates.

A creation request expires after ten minutes. Only a secret-authenticated `Update.managed_bot` can provide the candidate bot identity; callbacks never provide a bot ID. The creator must match the pending project's owner. The identity is reserved without a credential, and the owner confirms the connection. The factory retrieves the token with `getManagedBotToken`, checks its bot ID, verifies `getMe`, and encrypts it through the existing binding service. Publishing remains a separate explicit action. No token enters conversation state or responses.

Duplicate update IDs are suppressed by the existing transactional ledger. Updates without a pending request do not create projects. Ownership-change updates for a known bot disable its runtime, mark its project as needing attention, and remove the previous project's stored credential. Pending confirmation locks the project and refuses invalidated candidates. Automatic ownership migration and managed-token rotation are not implemented; existing connection controls support verified replacement tokens for the same bot.

The settings panel also changes the connected bot's Telegram display name, description and short bio, with Telegram field limits and project permissions. These changes apply immediately; project rename remains separate.

References: https://core.telegram.org/bots/features#managed-bots and https://core.telegram.org/bots/api#managedbotupdated.

Validation: mocked unit tests cover expiry, forged confirmation, mismatched token identity, unavailable manager mode, ownership invalidation and profile updates. The disposable PostgreSQL CI test exercises native update parsing, pending identity reservation, duplicate delivery and encrypted credential binding. A real native creation still requires Bot Management Mode and an owner-confirmed creation in Telegram.
