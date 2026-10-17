# Preview deployment status — 2026-10-17

Vercel project: qmrsmithbot, linked to PhQMR7S/QMRSmithbot. Development remains on feat/account-language-preferences / draft PR #23; main is not merged or promoted.

Verified preview commit: a1c3362583c87325d0ebe83fc4a966f4bf2f6d5e.
Preview dashboard: https://qmrsmithbot-4rpy2ewrz-phqmr7s.vercel.app/dashboard

Authenticated deployment fetch checks:
- GET /health: 200, service status ok.
- GET /dashboard: 200, dashboard HTML present.
- GET /api/v1/projects without app credentials: 401.

The first preview built but failed at runtime because httpx was a development-only dependency despite an unconditional OIDC import. Moved it to production dependencies, redeployed and verified the endpoints above. CI now includes a separate runtime-only install/import/asset/authentication smoke job to prevent this class of failure. The smoke script was also exercised locally; the new isolated GitHub job has not yet been observed running.

Preview environment uses staging settings with development-session bootstrap disabled and the Telegram factory disabled. Vercel's default deployment protection remains in place. No app login provider, factory bot credential or database URL has been configured. The factory administrator ID is configured in preview environment variables, outside source control. This preview is a UI/server startup milestone, not a live bot.

Database provisioning blocker: the connected Neon organization is Vercel-managed and on the free plan. Creating a separate Neon project through its API was rejected with `action restricted; organization is managed by Vercel`. No database was created or migrated. Existing QMRMed databases/branches were not modified. Provision a dedicated free Neon resource from Vercel Storage/Marketplace and attach it to qmrsmithbot. Browser-based provisioning is currently blocked by a separate Vercel login; connector authentication does not authenticate that browser.

Next: connect the database, apply and test migrations, configure production-compatible identity/rate limiting and factory secrets, redeploy, then validate the factory webhook before activation. Generated-bot queue execution and advanced template types remain separate incomplete work.
