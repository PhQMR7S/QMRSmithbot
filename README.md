# QMRSmithbot

Production-oriented Telegram bot builder platform foundation.

## Architecture

The platform is designed as a multi-tenant control plane and runtime with:

- Authentication, identity, sessions, tenant isolation, roles, and permissions
- Visual workflow definitions and validation
- Versioned project lifecycle with publish/rollback
- Telegram bot provisioning and durable workflow runtime foundations
- Platform-level access policies
- Async queues/workers, observability, audit, and security controls

## Security boundary

The request path is intentionally layered:

`User → Identity → Session/Token → Principal → Tenant → Membership/Role → Permission → Project`

Production authentication fails closed until a real identity-provider adapter is explicitly configured. Development bootstrap sessions are unavailable in production.

## Development

```bash
pip install -e '.[dev]'
ruff check .
python -m compileall -q src tests migrations
alembic upgrade head --sql
pytest
```

Database migrations must be applied before starting application workers.

## Current status

Development branch capabilities now include:

- Arabic/English account preferences and a responsive same-origin `/dashboard`.
- Versioned starter templates for welcome, exact text replies and command responses.
- Tenant-scoped project search, rename, stop/resume and workflow draft/publish lifecycle.
- Opt-in private Telegram factory menus, persistent draft wizard and per-update deduplication.
- Vercel FastAPI entrypoint preparation.

The private Telegram factory is connected at @Manjerxbot. Factory chat supports encrypted bot-token binding, welcome/reply/command editing, previews, confirmed publication, stop/resume, and scoped statistics. The runtime also supports nested buttons/files and contact bots with owner reply routing. Static replies use Telegram webhook responses; contact copies use bounded Bot API calls. Enable it only after applying migrations and deploying the authenticated child ingress.

Advanced workflow actions (HTTP, delays, branching, variables and action chains) still require the separate durable queue runtime. Its activation gate remains disabled. Telegram login is available when configured; existing OIDC identities remain separate until explicit account linking is implemented. There is no fixed project-count cap, but provider and execution limits still apply.

See `docs/BUTTONS_AND_CONTACT.md` and `docs/INLINE_TEXT_RUNTIME.md` for runtime boundaries, setup and retry semantics.

Read `docs/DASHBOARD.md`, `docs/TEMPLATES.md`, `docs/PROJECT_MANAGEMENT.md`, `docs/TELEGRAM_FACTORY.md` and `docs/VERCEL_DEPLOYMENT.md` for functionality, prerequisites and validation limits.

The form template supports text, numeric and choice questions with forward branches, version-frozen visitor sessions and an owner-only submissions inbox. See [Form builder](docs/FORM_BUILDER.md).

### Connection diagnostics

The native bot panel's Connection & token section includes a read-only diagnostic check for users with project-write permission. It verifies the token identity, checks whether Telegram's webhook matches this factory, and displays pending updates, historical delivery-error time, local runtime status and the elapsed time of two Telegram API requests. This is not an end-to-end visitor latency measurement. Raw Telegram errors, tokens and webhook URLs are not displayed. The check never resets the webhook or drops pending updates; API failures preserve connection settings.

### Guided native builder

Creating a bot now opens a capability detail page for each type. Button bots can start from an editable content library, service directory or community guide. A nested visitor preview runs before any project is created. Explicit confirmation creates an independent draft with its own button IDs; sample content is labeled and must be reviewed before publishing. Existing projects are never overwritten or automatically published. The native project hub shows setup steps, draft/published versions, type-specific controls and aggregate button/file counts, including pending uploads. A service directory is not a payment processor, and contact bots are not a multi-agent ticket platform.

### Button layout and official Telegram colors

Button bots support draft-only sibling reordering from the native editor, explicit separate/joined rows (up to three buttons per row), and Telegram's default, primary, success and danger styles. Color and row settings are also editable in the web studio and reflected in its visitor preview. Actual colors depend on the Telegram client/theme. Only publication changes the visitor menu. Reordering swaps two adjacent sibling keys under the project write lock, using a bounded neighbor lookup; it never changes creation timestamps, parents, another project's buttons, or published order. Existing menus retain chronological order until edited. Each page/folder begins a fresh row. No arbitrary CSS, custom-emoji IDs or internal order keys can be submitted through the studio API.

### Per-bot owner control panels

Published child bots expose `/admin` and an owner-only management button on `/start`. The factory's published-project card opens that bot's own control panel via `?start=admin`; it retains credential connection/recovery controls. Each child panel manages only its bound project: button/file editing and design, welcome/reply/command content, bot profile, connection diagnosis, publication, form inbox and pause/resume. The visual form editor remains a project-linked web studio. This is independent management UI, not a separate server or source-code export for every child.

Private owner identity and the callback message's bot author are checked before management. Child callbacks use a distinct namespace. The child store keeps its conversation under the project's owner-state record, separate from the factory conversation and other child bots. Project IDs supplied in callbacks are checked against the bound child project before access. Tokens and creation of unrelated projects are not available in the child panel. Visitor reception can be paused while the owner retains `/admin` access to resume; disabling the runtime or losing credentials still requires factory recovery. `/start` or the exit button leaves an active editor; `/cancel` returns to the child panel. Visitor messages are never interpreted as owner edits.

### Purpose-specific child workspaces and native form designer

Each child dashboard now separates Editing, Publishing/operation, Identity/settings, and a type-specific stored-data overview. The overview reports actual saved items, completed form submissions, or stored contact mappings/blocks; it does not invent visitor or latency metrics. The dashboard is tailored to button, contact, form and text bots.

Form owners can design entirely inside Telegram: add text/number/choice questions, edit prompts/title/completion, change types and required flags, set numeric limits, replace choice labels, configure forward choice paths/finish, reorder, and explicitly confirm deletion. Replacing choice labels resets those choices' paths to Next, with a notice before input. Changing type resets its choices and numeric limits. The same validated Form schema and version table are used by native and web editors. Every write checks the expected version under the project lock. Invalid ranges, non-finite numbers, backward/missing paths, deleting the last question or a targeted question are rejected without saving. Visitors retain their original published form snapshot. The web editor remains an optional alternative; native form design does not require it.
