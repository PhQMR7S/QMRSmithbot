# Project management API

- GET /api/v1/projects: tenant-scoped list with query, status, limit (1–100), offset and has_more. Stable UUID ordering and literal, case-insensitive search; wildcard characters are escaped. This is page size, not a maximum number of projects. Offset pagination can shift if projects are created concurrently.
- PATCH /api/v1/projects/{id}: rename with {"name":"New name"}; requires PROJECT_WRITE.
- POST /api/v1/projects/{id}/stop: requires PROJECT_PUBLISH; sets stopped and retains workflow versions.
- POST /api/v1/projects/{id}/resume: requires PROJECT_PUBLISH and an active published workflow. Draft/error states return 409. Repeated stop/resume calls are safe for their existing state; resuming rechecks the published version.

Listing requires PROJECT_READ. Each operation uses the authenticated tenant; no caller-supplied owner or tenant field is accepted. Changes lock the project row within the request database transaction and generate an audit event. Other-tenant project IDs return the same not-found result as absent IDs.

Stopping prevents new workflow dispatch plans from being selected by the existing dispatcher; already claimed actions or running executions may finish. It does not revoke credentials, deactivate webhooks, or guarantee immediate cancellation. Resuming changes the logical runtime state only: live infrastructure and credentials are still required.

This change adds backend capabilities, not a finished web or Telegram administration UI. Database tests mock AsyncSession; actual PostgreSQL locking and concurrent transaction behavior still need integration validation.
