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
- [ ] On app load (and on any request that fails with a timeout/network
      error before the user is authenticated), show a banner: "Waking up the
      server — this can take up to 30 seconds on the first request," with a
      spinner
- [ ] Retry the health check / original request automatically until it
      succeeds (bounded retries with backoff, not an infinite hammer)
- [ ] Banner disappears once the backend responds normally; does not
      reappear on subsequent fast requests

### Tests
- [ ] Component/hook test: simulated slow/failing first `/health` call shows
      the banner, then clears once the mocked call succeeds
- [ ] No regression to normal (fast backend) load — banner never flashes

### Definition of Done
- Manual check: after leaving the Azure backend idle, first page load shows
  the waking-up message and resolves without the user seeing raw errors

---

## Phase D4 — GitHub Pages deployment pipeline

**Goal:** frontend auto-deploys to GitHub Pages as static files, no container.

### Subtasks
- [ ] Decide GitHub Pages mode (project page under `/<repo>/` vs. a custom
      domain) and set `vite.config.js`'s `base` accordingly
- [ ] `.github/workflows/deploy-frontend.yml`: on push to `main` (or manual
      dispatch) — `npm ci`, `npm run build` with `VITE_API_BASE_URL` set from
      a repo variable, then deploy via `actions/upload-pages-artifact` +
      `actions/deploy-pages`
- [ ] Enable GitHub Pages in repo Settings -> Pages, source = GitHub Actions
- [ ] No SPA-routing fallback (`404.html`) needed — app has no
      client-side router (single-page, state-driven screens), confirmed via
      `frontend/src` (no `react-router` dependency)

### Tests / Verification
- [ ] Workflow run succeeds on push to `main`
- [ ] Deployed Pages URL loads the app shell and static assets (no 404s from
      a wrong `base` path)

### Definition of Done
- Pushing to `main` auto-deploys the frontend to GitHub Pages
- Page loads correctly at the Pages URL

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
- [ ] Phase D3 — Frontend cold-start UX
- [ ] Phase D4 — GitHub Pages deployment pipeline
- [ ] Phase D5 — Azure backend (re)deploy with lessons applied
- [ ] Phase D6 — End-to-end verification

**Rule:** do not advance until every subtask in the current phase is `[x]`.
