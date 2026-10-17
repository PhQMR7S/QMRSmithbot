# Extensible template catalog

GET /api/v1/templates?language_code=ar|en returns versioned starter templates for authenticated accounts. POST /api/v1/templates/{template_id}/projects creates a project and its first workflow draft in the request database transaction. Requires the current tenant's PROJECT_WRITE permission. Does not publish, provision a Telegram bot, activate a webhook, or start a runtime.

Available starters:
- welcome: /start sends a configurable welcome.
- auto-replies: /start plus exact text matching with configured replies.
- command-menu: /start plus command-to-response mappings. This is text command routing, not an inline keyboard editor or automatic setMyCommands registration.

Example JSON body:
```json
{"name":"My FAQ","language_code":"ar","welcome":"أهلًا بك","rules":[{"trigger":"السعر","response":"اسأل الإدارة عن السعر"}]}
```

Text matching is exact and case-sensitive. Commands use lowercase ASCII, digits and underscores, begin with a letter and cannot override start. A blank name, duplicate rule trigger, slash-prefixed text trigger, unknown template or invalid locale is rejected before project creation. Caller cannot supply tenant or owner IDs.

The catalog is code-defined and extended through reviewed Template entries. No arbitrary Python execution, dynamic plugin installation, admin catalog editor or billing is included. No fixed project-count cap is imposed by this route. Existing resource limits (100 reply rules, bounded workflow size and message length) protect execution and are not claims of unlimited infrastructure.

Generated content language is selected at creation; it does not implement per-chat language switching. End-user preferences, Telegram factory menus, dashboard UI, support routing, moderation, competitions, subscriptions, stores, courses, AI, scheduling and queue adaptation remain separate implementation work. The catalog deliberately does not present those as available.

Validation uses the existing workflow schema and the real event classifier/trigger resolver. API tests use an in-memory project store. Live PostgreSQL transactions, deployed action delivery and Telegram integration still require integration validation.
