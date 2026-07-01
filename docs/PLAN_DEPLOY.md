# PLAN_DEPLOY.md — Deployment (revised architecture)

Supersedes `docs/Plan.md` Phase 10. Same execution rules apply: one phase per
session, tick checkboxes as completed, write/keep tests where noted, commit
after each phase, never commit secrets.

## 0. Why this replaces the original Phase 10 plan

The original Phase 10 put both frontend and backend on Azure App Service (F1,
container). During the first deploy attempt this hit a nasty failure mode
that's worth recording so it isn't repeated:

- Azure App Service **Free (F1)** tier gives the whole **App Service Plan** a
  shared daily CPU quota (~60 min). If a container crash-loops (e.g. missing
  required env var, bad registry auth), Azure restarts it rapidly and burns
  the *entire day's* quota in minutes — for every app on that plan, not just
  the broken one.
- Once `QuotaExceeded`, the site (including Kudu/SCM log access) is disabled
  until the next daily reset, so you can't even see why it crashed.
- This happened twice: once because required app settings didn't exist yet
  when the Web App was created, once because adding registry credentials
  triggered a restart that re-tripped the same quota — on **both** apps,
  because they shared one plan.
- The resource group (`examprep-trainer-rg`) from that attempt no longer
  exists and must be recreated.

**Architecture change to avoid repeating this:**

| Layer | Was (Plan.md Phase 10) | Now |
|-------|------------------------|-----|
| DB | Neon Postgres | Neon Postgres (unchanged, already provisioned) |
| Backend | Azure App Service (container) | Azure App Service (container) — **unchanged**, but now the *only* app on its plan |
| Frontend | Azure App Service (container, Nginx) | **GitHub Pages** (static build, no container) |
| CORS | None needed (Nginx same-origin proxy) | **Required** — frontend and backend are now different origins |
| Cold start | Both apps idle/cold-start | Only the backend cold-starts; frontend (GitHub Pages CDN) never does — **must show a "waking up" message** while the backend warms up |

Putting only the backend on Azure means the F1 plan's quota is no longer
shared with an unrelated frontend container — the single biggest cause of
the original outage is structurally gone.

---

## Phase D1 — Backend: CORS + Neon cutover (dev)

**Goal:** backend accepts cross-origin requests from the GitHub Pages origin,
and local dev talks to the real Neon DB instead of SQLite (already decided;
finish wiring it here).

### Subtasks
- [x] Confirm `backend/.env`'s `DATABASE_URL` points at the Neon connection
      string (not `sqlite:///./prep.db`) and the backend boots against it
      locally (`alembic upgrade head` succeeds, app starts)
- [x] Add a `cors_allowed_origins` (comma-separated) setting to
      `app/config.py`, sourced from `.env` / Azure App Settings
- [x] Add `CORSMiddleware` in `app/main.py`, restricted to the configured
      origin(s) — **no wildcard**, since requests carry `Authorization`
      headers
- [x] Document the setting in `backend/.env.example`

### Tests
- [x] `TestClient` request with `Origin: <allowed>` header gets
      `Access-Control-Allow-Origin` back
- [x] Request with an unlisted `Origin` does not get the CORS header
- [x] Existing test suite still green against Neon (or SQLite in CI — CI can
      keep using SQLite; only local dev needs to hit Neon)

### Definition of Done
- Local backend runs against Neon
- `pytest` green
- CORS only allows the intended frontend origin(s)

---

## Phase D2 — Frontend: absolute API base URL

**Goal:** `frontend/src/api.js` can target an absolute backend URL (for
GitHub Pages) while still working with the existing relative-path dev proxy
(`vite.config.js`) with zero behavior change locally.

### Subtasks
- [x] Add `VITE_API_BASE_URL` (empty string by default) read via
      `import.meta.env`
- [x] Introduce a single `apiUrl(path)` helper in `api.js` that prefixes
      `VITE_API_BASE_URL` onto every request path; use it in `publicRequest`
      and `fetchAuthenticated` (`streamAnswer` goes through
      `fetchWithRefresh` -> `fetchAuthenticated`, so it's covered too)
- [x] Documented in `frontend/.env.example` instead of committing a
      `.env.production` with a real URL — the Azure backend doesn't exist
      yet (recreated in Phase D5); the GitHub Actions workflow in Phase D4
      will set `VITE_API_BASE_URL` at build time from a repo variable once
      the backend URL is known

### Tests
- [x] Existing Vitest suite passes unchanged (4 pre-existing failing test
      files, unrelated to `api.js`, confirmed identical before/after via
      `git stash -u`)
- [x] Unit test for `apiUrl()`: empty base -> unchanged relative path;
      non-empty base -> `base + path` (`src/api.test.js`)

### Definition of Done
- `npm run dev` behavior against the local backend is unchanged
- `apiUrl()` produces an absolute backend URL when `VITE_API_BASE_URL` is set
- `vitest` shows no new failures vs. baseline

---

## Phase D3 — Frontend: cold-start UX

**Goal:** first request after Azure idle (~20-30s cold start) shows a clear
message instead of looking broken.

### Subtasks
- [x] On app load, show a banner: "Waking up the server — this can take up
      to 30 seconds on the first request," with a spinner. Implemented as a
      `useServerWakeup()` hook (`frontend/src/hooks/useServerWakeup.js`) that
      gates the whole app on a `/health` check (`checkHealth()` in
      `frontend/src/api.js`) before `LoginScreen`/`AppShell` ever renders —
      so an unauthenticated user can't hit the login form (and get a raw
      network error) while the backend is still cold
- [x] Retry the health check automatically until it succeeds (bounded
      backoff: `1s, 2s, 4s, 8s, 8s, 8s` ≈ 30s total, matching Azure's typical
      cold-start window), then stop and expose a manual "Retry" button
      (`WakingBanner.jsx`) instead of retrying forever
- [x] Banner disappears once the backend responds normally; does not
      reappear on subsequent fast requests (gating happens once, at the app
      root, not per-request)

### Tests
- [x] Hook test (`useServerWakeup.test.js`, fake timers): fast success never
      shows the banner; slow/failing first call shows it after a 400ms
      grace period and clears once a retry succeeds; bounded retries stop
      and `retryNow()` starts a fresh check
- [x] No regression to normal (fast backend) load — banner never flashes
      (400ms flash-delay grace period before `waking` is set); full frontend
      suite re-run shows the same 4 pre-existing failing files (13 tests,
      unrelated to this change) as the D2 baseline, with all new/updated
      tests (`App.test.jsx`, `useServerWakeup.test.js`) passing

### Definition of Done
- Manual check: after leaving the Azure backend idle, first page load shows
  the waking-up message and resolves without the user seeing raw errors —
  **not yet verified against a real deployed cold Azure backend** (D5 hasn't
  recreated it yet); logic is verified via the hook tests above plus a local
  dry run against the dev backend (booted uvicorn + vite dev server, `/health`
  returns `{"status":"ok"}` immediately, confirming the fast-path shows no
  banner). Full browser verification of the actual cold/slow path wasn't
  possible in this sandbox (headless Chromium is missing system libraries
  and no passwordless sudo is available to install them)

---

## Phase D4 — GitHub Pages deployment pipeline

**Goal:** frontend auto-deploys to GitHub Pages as static files, no container.

### Subtasks
- [x] Decide GitHub Pages mode: **project page** under `/ExamPrepTrainer/`
      (no custom domain) — repo is `AntHavrylov/ExamPrepTrainer`, so Pages
      serves at `https://anthavrylov.github.io/ExamPrepTrainer/`. Set
      `vite.config.js`'s `base` to `/ExamPrepTrainer/` for the production
      build only (dev server and vitest keep `base: '/'`, via a
      `command === 'build'` check) — confirmed locally via `npm run build`:
      emitted `dist/index.html` references `/ExamPrepTrainer/assets/...`
- [x] `.github/workflows/deploy-frontend.yml`: on push to `main` (path-
      filtered to `frontend/**`) or manual dispatch — `npm ci`, `npm run
      build` with `VITE_API_BASE_URL` from the `vars.VITE_API_BASE_URL` repo
      variable (empty until Phase D5 gives us the Azure backend URL), then
      `actions/upload-pages-artifact` + `actions/deploy-pages`
- [ ] Enable GitHub Pages in repo Settings -> Pages, source = GitHub Actions
      — **manual step, not done yet**: no `gh` CLI in this environment and
      it's a repo-settings change, so needs to be done by hand (or by the
      user) before the workflow's `deploy` job can succeed
- [x] No SPA-routing fallback (`404.html`) needed — app has no
      client-side router (single-page, state-driven screens), confirmed via
      `frontend/src` (no `react-router` dependency)

### Tests / Verification
- [ ] Workflow run succeeds on push to `main` — **not yet verified**; needs
      Pages enabled (above) and an actual push, neither done yet
- [ ] Deployed Pages URL loads the app shell and static assets (no 404s from
      a wrong `base` path) — **not yet verified against a live deploy**;
      `base` path correctness confirmed locally via `npm run build` output

### Definition of Done
- Pushing to `main` auto-deploys the frontend to GitHub Pages — **workflow
  written, not yet exercised** (Pages isn't enabled yet)
- Page loads correctly at the Pages URL — **pending** the above

---

## Phase D5 — Backend: Azure (re)deploy with lessons applied

**Goal:** backend runs reliably on Azure App Service F1, without repeating
the quota-exhaustion incident.

### Subtasks
- [ ] Recreate resource group + App Service Plan (F1, Linux) + **one** Web
      App (backend only — frontend no longer lives here)
- [ ] Before/atomically with `az webapp create`, set **all** required app
      settings so the container never boots without them: `DATABASE_URL`
      (Neon), `SECRET_KEY`, `API_KEY_ENCRYPTION_KEY`, `WEBSITES_PORT=8000`,
      `FRONTEND_ORIGIN` (GitHub Pages URL, for CORS)
- [ ] Confirm the GitLab Container Registry deploy token's scope actually
      covers the backend image's project *before* setting
      `DOCKER_REGISTRY_SERVER_USERNAME/PASSWORD` (this was the suspected
      cause of the second quota burn)
- [ ] Immediately after `az webapp start` / any settings change that forces a
      restart: `az webapp log tail` (or poll the Kudu docker-logs API) right
      away — don't just poll `/health` — so a crash reason is captured before
      quota can run out
- [ ] Run `alembic upgrade head` against Neon (already wired into the
      Docker `CMD`) and confirm tables exist

### Tests / Verification
- [ ] `az webapp show` reports `state=Running`, `usageState=Normal` shortly
      after creation (not `QuotaExceeded`)
- [ ] `curl https://<backend-app>.azurewebsites.net/health` -> `{"status":"ok"}`
- [ ] Neon has the expected tables after first boot

### Definition of Done
- Backend reachable at its Azure URL
- DB is Neon, migrations applied
- App stays in `Running`/`Normal` state (quota incident not repeated)

---

## Phase D6 — End-to-end verification

**Goal:** full production flow works: GitHub Pages frontend -> Azure backend
-> Neon DB.

### Subtasks
- [ ] Full browser flow on production URLs: register -> login -> create
      section -> add text -> start session -> answer -> score -> summary
- [ ] Confirm cold-start banner appears on first hit after backend idle, and
      clears once it wakes
- [ ] Confirm no CORS errors in the browser console; auth/refresh flow works
      cross-origin (JWT via header + localStorage — no cookies, so no
      SameSite concerns)
- [ ] Update `docs/Plan.md` Phase 10 checkboxes to reflect this plan's
      completion

### Definition of Done
- Full flow works on public URLs (GitHub Pages + Azure + Neon)
- No secrets in the repo
- `docs/Plan.md` Phase 10 marked complete, pointing at this file

---

## Phase checklist

- [x] Phase D1 — Backend CORS + Neon cutover (dev)
- [x] Phase D2 — Frontend absolute API base URL
- [x] Phase D3 — Frontend cold-start UX
- [ ] Phase D4 — GitHub Pages deployment pipeline
- [ ] Phase D5 — Azure backend (re)deploy with lessons applied
- [ ] Phase D6 — End-to-end verification

**Rule:** do not advance until every subtask in the current phase is `[x]`.
