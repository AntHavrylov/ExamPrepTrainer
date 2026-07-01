# Plan.md — Interview/Exam Prep Trainer (AI-powered)

A web app for interview and exam preparation. A user registers, fills their own
knowledge-base sections with plain text, selects one or more sections, picks a task
type (technical / behavioral / mixed) and a training format (open-ended Q&A or
multiple-choice quiz), and the AI generates questions, accepts answers, and scores
them with feedback. Each user's data is private.

> **Execution:** this plan is carried out by an AI coding agent (Claude Code).
> Each phase is a separate, verifiable step with its own checklist, tests, and
> Definition of Done.

---

## 0. Stack decisions

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | **Python + FastAPI** | Async, OpenAI-compatible clients, built-in OAuth2 |
| Frontend | **React + Vite** | Simplest modern frontend, great AI codegen |
| ORM | **SQLAlchemy 2.x** | Write once, swap DB via config |
| Migrations | **Alembic** | Evolve schema across phases without data loss |
| DB (local) | **SQLite** | Zero setup, file on disk |
| DB (prod) | **Neon** (Postgres, free) or **Supabase** | Free tier, Postgres |
| **Auth** | **FastAPI + JWT** (passlib/bcrypt) | Self-contained, no vendor lock |
| AI | **OpenRouter** (OpenAI-compatible API) | One key, has `:free` models |
| Tests | **pytest + httpx TestClient** | Standard, fast; AI client is mocked |
| Deploy backend | **Azure App Service** (Free F1 tier), container pulled from **GitLab Container Registry** | Free; reuses existing Azure account. No "Always On" on Free tier, so it idles and cold-starts (~20-30s) after inactivity. GitLab CR avoids Azure Container Registry's cost |
| Deploy frontend | **Azure App Service** (Free F1 tier), container pulled from **GitLab Container Registry** | Free; same Azure account/subscription as the backend; uses existing `frontend/Dockerfile` (Nginx). Also idles/cold-starts (~20-30s) on Free tier |

**Task types** (user choice): `technical`, `behavioral`, `mixed`.

**Format** (user choice, per session): `open_ended` (free-text answer, AI-scored
via `evaluate_answer`) or `quiz` (multiple-choice, auto-graded by comparing the
selected option to a server-stored correct index — no AI call needed to score).

> Auth alternative: if you use Supabase for the DB anyway, you can offload
> register/login to **Supabase Auth** (less code, JWT out of the box). The primary
> path below is self-hosted JWT on FastAPI.

---

## Agent operating instructions (READ FIRST)

The coding agent must follow these rules on every phase:

1. **Work one phase per session.** Do not start the next phase until the current
   one is fully done.
2. **Tick the checkboxes** in this file as you complete each subtask. Edit `Plan.md`
   to mark `- [x]`.
3. **Write tests for every phase** (see each phase's "Tests" block). Backend tests
   use `pytest`. The OpenRouter client MUST be mocked in tests — never call the real
   AI API in the test suite (it is flaky and rate-limited).
4. **Before marking a phase done:** run the full test suite (`pytest`) and confirm
   it is green, AND confirm every subtask checkbox in the phase is `[x]`.
5. **Commit after each phase** with a message like `feat(phase-N): <summary>`.
6. **Secrets:** add `.env` to `.gitignore` in Phase 1. Never commit keys.
7. If a Definition of Done item fails, fix it before proceeding — do not skip.

---

## Repository structure (final)

```
prep-trainer/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI entrypoint
│   │   ├── config.py          # settings from .env
│   │   ├── db.py              # SQLAlchemy connection
│   │   ├── models.py          # ORM models (User, Section, ...)
│   │   ├── schemas.py         # Pydantic schemas
│   │   ├── auth/
│   │   │   ├── security.py    # password hashing, JWT
│   │   │   └── deps.py        # get_current_user
│   │   ├── ai/
│   │   │   ├── client.py      # OpenRouter wrapper (mockable)
│   │   │   ├── generate.py    # question generation (open-ended + quiz)
│   │   │   └── evaluate.py    # answer evaluation
│   │   └── routers/
│   │       ├── auth.py        # register / login / me
│   │       ├── sections.py    # knowledge-base CRUD (user-scoped)
│   │       ├── sessions.py    # training sessions (user-scoped)
│   │       └── ai.py          # generate / evaluate
│   ├── alembic/               # migrations
│   ├── tests/                 # pytest
│   ├── requirements.txt
│   └── .env                   # secrets (gitignored!)
└── frontend/                  # React + Vite
```

---

## Phase 1 — Backend skeleton

**Goal:** boot FastAPI with a health endpoint.

### Subtasks
- [x] Create venv and install `fastapi uvicorn[standard] pydantic-settings`
- [x] Add `.gitignore` (include `.env`, `*.db`, `__pycache__`, `.venv`)
- [x] `app/main.py` with `GET /health` -> `{"status": "ok"}`
- [x] `app/config.py` loading settings from `.env`
- [x] Run with `uvicorn app.main:app --reload`

### Tests
- [x] `pytest` setup with `httpx` TestClient
- [x] Test: `GET /health` returns 200 and `{"status":"ok"}`

### Definition of Done
- `curl /health` returns `{"status":"ok"}`
- `/docs` works
- `pytest` is green

---

## Phase 2 — Auth & users (foundation)

**Goal:** registration/login, JWT, protected endpoints. Done early so all later
models carry `user_id` from the start. Set up Alembic now.

### Subtasks
- [x] Install `sqlalchemy alembic python-jose[cryptography] passlib[bcrypt] python-multipart`
- [x] `db.py`: SQLite engine (`sqlite:///./prep.db`), `SessionLocal`, `Base`
- [x] Initialize Alembic; create first migration for `User`
- [x] `User` model: `id`, `email` (unique), `hashed_password`, `created_at`
- [x] `auth/security.py`: bcrypt hashing, JWT create/verify
- [x] `auth/deps.py`: `get_current_user` dependency
- [x] `routers/auth.py`: `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- [x] `SECRET_KEY`, token TTL in `.env` + `config.py`

### Tests
- [x] Register a user -> 201; duplicate email -> 400/409
- [x] Login with correct creds -> JWT; wrong creds -> 401
- [x] `GET /auth/me` without token -> 401; with token -> user data
- [x] Password stored only as hash (assert raw password not in DB)

### Definition of Done
- Two distinct users can register and log in
- Protected route rejects missing/invalid tokens
- Alembic migration runs cleanly
- All checkboxes `[x]`, `pytest` green

---

## Phase 3 — Knowledge base + plain-text editing (user-scoped)

**Goal:** each user creates their own sections and **fills/edits them as plain
text**. First-class feature, not just seeding.

### Subtasks
- [x] `Section` model: `id`, `user_id (FK)`, `name`, `description`, `created_at`
- [x] `Document` model: `id`, `section_id (FK)`, `title`, `content (text)`, `updated_at`
- [x] Alembic migration for the new models
- [x] `routers/sections.py` (all under `get_current_user`, filtered by `user_id`):
  - [x] `POST /sections` — create section
  - [x] `GET /sections` — only own sections
  - [x] `GET /sections/{id}` — section with documents
  - [x] `POST /sections/{id}/documents` — add plain text
  - [x] `PUT /documents/{id}` — edit plain text
  - [x] `DELETE /documents/{id}` — delete fragment
- [x] Enforce ownership: accessing another user's section/document -> 403/404
- [x] Add input limits (max content length per document, max sections per user)

### Tests
- [x] User A creates a section, adds text, edits it, deletes it
- [x] User B cannot see User A's sections (list is empty for B)
- [x] User B editing A's document -> 403/404
- [x] Oversized content -> 422

### Definition of Done
- A logged-in user creates a section, pastes notes as text, then edits/appends
- Cross-user isolation verified by tests
- All checkboxes `[x]`, `pytest` green

---

## Phase 4 — OpenRouter connection

**Goal:** confirm AI calls work; make the client mockable.

### Subtasks
- [x] Create OpenRouter account + API key
- [x] `.env`: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (a `:free` model)
- [x] Install `httpx`
- [x] `ai/client.py`: async wrapper (URL `https://openrouter.ai/api/v1/chat/completions`,
      header `Authorization: Bearer <key>`); function takes messages, returns text
- [x] Make the client injectable so tests can override it (FastAPI dependency)
- [x] Temporary `GET /ai/ping` (protected) -> "Say hello in one word"
- [x] Error handling: missing key / rate limit / timeout do not crash the server
- [x] Add retry with backoff on 429/5xx

### Tests
- [x] With a **mocked** client, `/ai/ping` returns the canned response
- [x] Mocked rate-limit error -> graceful 503/handled response, no crash

### Definition of Done
- `/ai/ping` returns a live response (manual check with real key)
- Tests pass using the mock (no real API call in CI)
- All checkboxes `[x]`, `pytest` green

---

## Phase 5 — Question generation

**Goal:** AI generates questions from selected sections and task type.

### Subtasks
- [x] `ai/generate.py`: `generate_questions(sections, mode, count)`
  - [x] Gather content of the **current user's** selected sections
  - [x] Apply a token budget: truncate/limit content so the prompt can't overflow
  - [x] System prompt sets interviewer role; ask for **strict JSON** array of `{question, category}`
- [x] Safe JSON parsing (strip ```json fences, try/except, one retry on parse fail)
- [x] `POST /ai/generate` (protected): input `section_ids[]`, `mode`, `count`
  - [x] Validate all sections belong to the user
  - [x] Cap `count` (e.g. max 20) to control cost
- [x] Mode logic: technical / behavioral / mixed (~50/50)

### Tests
- [x] With mocked AI returning valid JSON -> parsed list of questions
- [x] Mocked AI returning JSON wrapped in prose/fences -> still parsed
- [x] Requesting another user's section -> 403/404
- [x] `count` over the cap -> 422

### Definition of Done
- For a real section + `technical`, questions are relevant (manual check)
- Parser handles messy model output
- All checkboxes `[x]`, `pytest` green

---

## Phase 6 — Answer evaluation

**Goal:** AI scores the user's answer and gives feedback.

### Subtasks
- [x] `ai/evaluate.py`: `evaluate_answer(question, answer, context)`
  - [x] Returns **strict JSON**: `{score: 0-10, feedback, strengths[], gaps[]}`
  - [x] Use low temperature (0 or near-0) for more consistent scoring
- [x] Criteria in prompt tied to question type (technical -> accuracy/depth;
      behavioral -> STAR structure)
- [x] `POST /ai/evaluate` (protected): `question`, `answer`, `section_ids[]`
- [x] Clamp/validate score to 0–10; handle non-numeric model output

### Tests
- [x] Mocked weak answer -> low score + non-empty `gaps`
- [x] Mocked strong answer -> high score + non-empty `strengths`
- [x] Score always coerced into 0–10 integer

### Definition of Done
- Manual check: weak vs strong answers get sensibly different scores
- All checkboxes `[x]`, `pytest` green

---

## Phase 7 — Sessions & persistence (user-scoped, open-ended + quiz)

**Goal:** persist each user's training run and history. The user picks, at session
start, both a task type (`technical`/`behavioral`/`mixed`) and a **format**:
`open_ended` (free-text, AI-scored) or `quiz` (multiple-choice, auto-graded). This
is also where quiz-mode question generation is built, since hiding the correct
answer from the client until it's submitted requires server-side state — which
only exists once Sessions/Attempts are persisted.

### Subtasks
- [x] `Session` model: `id`, `user_id (FK)`, `mode`, `format` (`open_ended` | `quiz`),
      `section_ids`, `started_at`, `finished_at`
- [x] `Attempt` model: `id`, `session_id (FK)`, `question`, `category`, `format`,
      `options` (JSON list, quiz only), `correct_index` (quiz only — **never**
      serialized in any response before the answer is submitted), `selected_index`
      (quiz only), `answer` (free text, open-ended only), `score`, `feedback`,
      `created_at`
- [x] Alembic migration for the new models
- [x] `ai/generate.py`: `generate_quiz_questions(sections, mode, count)` — reuses
      the same char-budgeted `build_context` and mode instructions as
      `generate_questions`, but the strict-JSON schema is
      `{question, category, options: [4 strings], correct_index: 0-3}`; reuse the
      shared JSON-parsing helper and the one-retry-on-parse-fail behavior
- [x] `routers/sessions.py` (all under `get_current_user`, filtered by `user_id`):
  - [x] `POST /sessions` — start a session; input `section_ids[]`, `mode`, `format`
  - [x] `POST /sessions/{id}/next` — generate the next question via
        `generate_questions` (open-ended) or `generate_quiz_questions` (quiz)
        depending on the session's `format`; for quiz, store `correct_index`
        server-side and respond with only `{question, category, options}` —
        no answer key
  - [x] `POST /sessions/{id}/answer`:
        - open-ended: body has free-text `answer` -> `evaluate_answer` -> store
          score/feedback
        - quiz: body has `selected_index` -> compare against the stored
          `correct_index` (deterministic, no AI call) -> score 10/0 + feedback
          that reveals the correct option
  - [x] `GET /sessions/{id}` — session summary (includes correct answers for any
        quiz attempts already submitted)
  - [x] `GET /sessions` — own session history (paginated)
- [x] Prevent duplicate scoring on double-submit (idempotency per attempt)

### Tests
- [x] Full open-ended cycle (mocked AI): start -> next -> answer -> stored attempt with score
- [x] Full quiz cycle (mocked AI): start -> next (response has no `correct_index`/
      answer field) -> answer with the correct index -> score 10; wrong index -> score 0
- [x] User sees only their own sessions
- [x] Double-submitting the same answer doesn't double-score (both formats)

### Definition of Done
- Full loop works via `/docs` for **both** formats: login -> start -> question ->
  answer -> score -> summary
- Quiz `next` responses never leak the correct answer before it's submitted
- History is user-isolated
- All checkboxes `[x]`, `pytest` green

---

## Phase 8 — Frontend (React + Vite)

**Goal:** make it usable in the browser, with login.

### Subtasks
- [x] `npm create vite@latest frontend -- --template react`
- [x] Configure dev proxy to backend
- [x] Auth context: store JWT, send `Authorization` header, handle 401 -> logout
- [x] **Login / Register** screen
- [x] **Sections** screen: list own sections, create, plain-text editor to fill content
- [x] **Start training** screen: section checkboxes + mode selector + format
      selector (open-ended Q&A or quiz)
- [x] **Training** screen: chat-like flow — question -> answer input -> score/feedback -> next
  - [x] Open-ended: free-text answer box
  - [x] Quiz: render `options` as selectable buttons instead of a text box;
        disable re-selection once answered, then show correct/incorrect + feedback
  - [x] Loading states while AI is working (calls take seconds)
- [x] **Summary** screen: questions, scores, average
- [x] State via React state/context (no extra libs needed)

### Tests
- [x] Light smoke tests (Vitest) for auth context and one screen render (optional)

### Definition of Done
- End-to-end in browser: register -> login -> fill a section with text -> train ->
  scores -> summary
- Logged-out user cannot reach protected screens
- All checkboxes `[x]`

---

## Phase 9 — Polish (iterative, one at a time)

- [x] Streaming responses (tokens appear progressively) — scoped to open-ended answer evaluation
- [x] Progress stats: score chart, "weakest topics"
- [x] Knowledge-base import: upload `.md`/`.txt` into a section
- [x] Refresh tokens (longer sessions without re-login)
- [x] Per-user rate limiting on AI endpoints (cost/abuse control)
- [x] RAG (scoped down: lightweight keyword-relevance ranking of document chunks when content exceeds the token budget, instead of embeddings + vector search)

---

## Phase 9.5 — Docker support (local containers)

**Goal:** run the whole app (frontend, backend, Postgres) locally via a single
`docker compose up --build`, as a dress rehearsal for Phase 10 deploy. Using
Postgres here (instead of SQLite) catches dialect/migration issues before the
real deploy. The frontend container serves the production build via Nginx,
which also reverse-proxies API paths to the backend — mirroring
`vite.config.js`'s dev proxy, so no frontend code changes are needed.

### Subtasks
- [x] Add `psycopg2-binary` to `backend/requirements.txt` (Postgres driver)
- [x] `backend/Dockerfile`: install deps, run `alembic upgrade head` then
      `uvicorn` on container start
- [x] `backend/.dockerignore` (`.venv`, `__pycache__`, `*.db`, `.env`, etc.)
- [x] `frontend/Dockerfile`: multi-stage `npm run build` -> `nginx:alpine`
- [x] `frontend/nginx.conf`: SPA fallback + reverse proxy `/auth`,
      `/sections`, `/documents`, `/ai`, `/sessions`, `/health` to the
      `backend` service
- [x] `frontend/.dockerignore` (`node_modules`, `dist`)
- [x] `docker-compose.yml` (repo root): `db` (Postgres + volume +
      healthcheck), `backend` (env_file reuses `backend/.env`, `DATABASE_URL`
      overridden to Postgres), `frontend` (depends on backend)

### Tests / Verification
- [x] `docker compose up --build` starts all 3 services without errors
- [x] `curl http://localhost:8000/health` -> `{"status":"ok"}` (backend direct)
- [x] `curl http://localhost:8080/health` -> same, via the Nginx proxy
- [x] Alembic creates tables in the Postgres container
- [x] Full browser flow against the containers: register -> login -> create
      section -> add text -> train -> answer -> score -> summary
- [x] `docker compose down -v` then `up --build` again works from a clean volume

### Definition of Done
- One command (`docker compose up --build`) brings up Postgres + backend +
  frontend locally
- Frontend at `http://localhost:8080` fully functional against the backend
  through Nginx, with zero frontend code changes
- Backend talks to Postgres (not SQLite) inside Docker
- All checkboxes `[x]`, verified manually (infra-only phase, no pytest changes)

---

## Phase 10 — Deploy

**Goal:** runs on the internet, for free.

> **Architecture revised — see `docs/PLAN_DEPLOY.md` for the current,
> detailed plan.** The first deploy attempt put both frontend and backend on
> Azure App Service (F1) sharing one plan; a crash-loop on either app burned
> the plan's entire shared daily CPU quota, taking both apps down
> (`QuotaExceeded`) twice. Revised architecture: **DB** stays Neon Postgres;
> **backend** stays on Azure App Service (now the *only* app on its plan, so
> it can no longer be starved by an unrelated container); **frontend** moves
> to **GitHub Pages** (static, no container, no cold start) instead of a
> second Azure Web App. Since frontend and backend are now different
> origins, the backend needs CORS middleware (previously avoided via
> same-origin Nginx proxying), and the frontend needs a "waking up the
> server" message for the backend's cold start. The subtasks below are kept
> for history; `docs/PLAN_DEPLOY.md` Phases D1–D6 are the authoritative
> checklist going forward.

### Subtasks (superseded by docs/PLAN_DEPLOY.md)
- [x] DB: create free Postgres on Neon; get connection string
- [ ] Backend: switch `DATABASE_URL` to Postgres; run Alembic migrations on deploy
- [x] Backend image built from the existing `backend/Dockerfile` and pushed to
      **GitLab Container Registry** (`registry.gitlab.com`, free, public project)
      instead of Azure Container Registry
- [x] Deploy backend to Azure App Service (Free F1 tier) configured as a
      "Container" Web App pulling from the GitLab Container Registry image
      (public project, no pull credentials needed); secrets in App Service
      Application Settings (not in code)
- [x] Frontend image built from the existing `frontend/Dockerfile` and pushed to
      **GitLab Container Registry**, same as the backend
- [x] Deploy frontend to Azure App Service (Free F1 tier) configured as a
      "Container" Web App pulling from the GitLab Container Registry image
- [x] Frontend proxies API calls to the backend via `frontend/nginx.conf.template`
      (envsubst-on-templates, `BACKEND_ORIGIN` env var) — browser only ever talks
      to the frontend's own origin, so **no CORS middleware needed** on the
      backend
- [x] Set Azure App Setting `BACKEND_ORIGIN=https://<backend-app>.azurewebsites.net`
      on the frontend Web App once the backend's real URL is known
- [ ] Note in README/UI that the first request after idle may take ~20-30s
      (Free tier cold start) — applies to both services

### Definition of Done
- See `docs/PLAN_DEPLOY.md` — Phase D6 (End-to-end verification) is the
  current Definition of Done for deploy.

---

## Phase checklist

- [x] Phase 1 — Backend skeleton + /health
- [x] Phase 2 — Auth + users (JWT, Alembic)
- [x] Phase 3 — Knowledge base + plain-text editing (user-scoped)
- [x] Phase 4 — OpenRouter connection (mockable)
- [x] Phase 5 — Question generation
- [x] Phase 6 — Answer evaluation
- [x] Phase 7 — Sessions + persistence (user-scoped, open-ended + quiz)
- [x] Phase 8 — React frontend with login
- [x] Phase 9 — Polish
- [x] Phase 9.5 — Docker support (local containers)
- [ ] Phase 10 — Deploy (see `docs/PLAN_DEPLOY.md`)

**Rule:** do not advance until every subtask in the current phase is `[x]` and the
test suite is green.
