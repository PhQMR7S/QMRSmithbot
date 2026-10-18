# Dashboard

Open /dashboard on the same API origin. The interface supports Arabic RTL and English LTR, authenticated workspace selection, project search/filter/pagination, rename, stop/resume, version listing/publishing, template draft creation and account language preferences.

The existing OIDC provider must be configured with AUTH_OIDC_REDIRECT_URI=https://YOUR_HOST/dashboard/callback and the same redirect registered at that provider. Login redirects to the server-selected HTTPS provider. The callback removes code/state from browser history, exchanges them using the existing backend endpoint, and keeps the bearer session only in page memory. Reloading requires login again. No factory bot token is required or collected by this UI. Production authentication and tenant permission checks remain server-side.

Assets are served from a fixed allowlist with a same-origin CSP, no-store caching, no-referrer and nosniff. Untrusted project names/errors are rendered with textContent, not HTML. No scripts, fonts or assets load from third parties. Only the non-sensitive local language choice may use localStorage.

UI implementation uses native ES modules and the existing FastAPI package, avoiding a second build/deployment stack. Packaged dashboard assets are included via setuptools package-data.

Current limits: no Telegram bot credential provisioning form, workflow graph editor, account/role administration, billing, competition tools or Telegram factory menus yet. API permission errors are shown; controls are not yet prefiltered by role. The template rules editor uses one keyword | response per line. Stop/resume/publish are logical control-plane changes, not infrastructure provisioning. The dialog confirms state changes; already-running tasks may finish. Actual PostgreSQL/OIDC/Telegram delivery validation and runtime setup remain deployment prerequisites.


## Browser validation

With Playwright and Chromium installed and the API listening locally, run `BASE_URL=http://127.0.0.1:8765 node tests/dashboard.browser.cjs`. Optional CHROMIUM_EXECUTABLE_PATH selects an installed Chromium; optional QA_SCREENSHOT_DIR writes local QA captures. The script intercepts API requests with explicit fixtures and does not exercise a live identity provider or production database.

Verified at the 1586×992 design reference viewport and 390×844 mobile viewport: callback URL cleanup, projects, rename, stop confirmation, empty search, draft creation, Arabic/English direction switch, no page-level horizontal overflow and no JavaScript exceptions. Both the Image Gen reference and rendered screenshots were visually inspected. Browser/IAB could not connect to the isolated local server, so local Playwright Chromium was used.

Visual comparison: white background, pale-slate sidebar, navy text and teal primary actions retained; RTL sidebar/header/table hierarchy retained; search and action labels retained; rounded inputs and table borders retained; clear title/body/control typography checked. Intentional functional differences: no stop button on an unpublished draft, real integer version values, explicit Versions buttons rather than unlabeled overflow controls, an explicit Search submit button, and no invented project descriptions or decorative icons. Mobile rows stack to keep all actions visible without sideways scrolling. Reference copy omissions reflect data the API does not provide, not hidden placeholder functionality.
