# Visual bot studio

The authenticated dashboard now opens a studio for the existing inline templates. All templates support draft welcome editing and a local visitor preview. Button bots additionally support hierarchical section, text, HTTPS link and file-placeholder creation, editing and deletion. Files are uploaded inside the connected child bot; the browser cannot submit a Telegram file ID. File IDs and credentials are excluded from studio responses.

Web and native editing use the same FactoryButtonRecord and WorkflowVersionRecord tables. No schema migration or secondary database is introduced. Project permissions and tenant membership apply to every endpoint. Project row locks serialize writes. Welcome edits require the expected workflow version; button edits/deletes require a hash of the current draft, parent and deletion state. An ID chosen once for each new button makes creation retries idempotent. File metadata is preserved on label edits. Publication still uses the native factory panel, which verifies the webhook and publishes button/file snapshots together. A generic workflow publication is no longer offered by the dashboard.

The UI preserves unsaved text on errors, shows conflict guidance, asks before discarding local edits, blocks edits during writes, ignores responses from obsolete studio instances and tenant switches, and escapes content through DOM textContent. Mobile users can switch between Design and Visitor preview. Preview actions never send Telegram messages or open external links.

## Entry and deployment

The native bot panel links to `https://qmrsmithbot-ingress.vercel.app/dashboard?project=UUID`. The page requires Telegram application sign-in before project data is accessible. Returning to the factory uses `/start project_UUIDHEX`, resolved through the existing tenant-scoped project panel.

The gateway now exposes a strictly enumerated subset of dashboard assets and APIs. Only authentication discovery and Telegram sign-in challenge operations are public; other API routes require a Bearer header at the gateway and full session/tenant authorization at the private application. Cross-origin writes, URL-borne credentials, arbitrary paths, upstream redirects and HTML API error pages are rejected. Hosting bypass credentials remain in outbound headers only. The main Vercel application's hosting protection remains enabled. This intentionally replaces the former webhook-only gateway boundary with authenticated dashboard access; it does not expose provisioning credentials, development authentication, documentation, arbitrary tenant administration or worker APIs.

## Reference decisions

Reviewed on 2026-10-18:
- sametcn99/tg-bot-studio (GPL-3.0): unified management, media reuse and visual conversation concepts. Its single-instance SQLite/polling runtime was not adopted.
- fedorabakumets/telegram-bot-builder (MIT): visual authoring and preview concepts. Arbitrary generated Python execution was not adopted.
- qilaidev/telegram-ui-builder (MIT): separate authoring/preview and validated button navigation concepts.
- laser54/telegram-managed-bot-factory: owner-confirmed creation and explicit reconciliation boundaries; the existing managed bot flow remains in use.
- aiogram: retained as the existing Bot API framework.

This implementation is original. No source files, assets, components or dependencies were copied from these projects; no third-party license is being substituted. Their advertised capabilities are references, not claims that every feature is now implemented here. A general flow canvas, conditions/delays, campaign broadcasting, payment processing and a Mini App runtime remain outside this studio release.

## Verification

Unit tests cover content validation, file-ID injection rejection, revision sensitivity, authentication and native return links. Gateway tests cover path/method allowlists, Bearer forwarding, tenant headers, cross-origin write rejection, payload bounds and no credential/redirect leakage. Disposable PostgreSQL CI tests exercise persisted drafts, retry deduplication, native/web conflicts, stale welcome versions and tenant/project scope. Playwright tests exercise real rendered desktop/mobile screens with mocked API data, including nested creation/deletion, preserved text on conflicts, literal script-like text, file upload links and language switching. A real signed-in user's Telegram file upload is not automated.
