# Language preferences foundation

The control-plane API now exposes Arabic and English metadata, direction (RTL/LTR), and a shared starter UI catalog:

- GET /api/v1/languages
- GET /api/v1/languages/{ar|en}/messages
- GET /api/v1/me/preferences (authenticated)
- PUT /api/v1/me/preferences with {"language_code":"ar"} or {"language_code":"en"} (authenticated)

Preferences use the existing nullable users.language_code field. No migration is required. Only the authenticated account can be updated; the request accepts no target user ID. Unsupported codes and extra fields are rejected. Null or unsupported stored values resolve to Arabic. The shared resolver accepts regional Telegram hints (ar-IQ, en-US) and prioritizes an explicit preference.

This is the backend foundation, not a completed language selector UI. Web dashboard and Telegram factory menus must consume these endpoints/catalogs in a subsequent change. It does not automatically translate user-authored workflow messages, localize API errors, or persist language preferences for end users of generated bots. No external translation service is used.

Tests cover locale resolution, metadata/catalog consistency, authenticated reads/writes, cross-account isolation, invalid input and missing accounts. Endpoint persistence tests use a fake session; a live PostgreSQL integration check remains required before deployment.
