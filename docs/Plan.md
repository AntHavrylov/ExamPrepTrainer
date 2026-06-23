# Plan.md — Interview/Exam Prep Trainer (AI-powered)

A web app for interview and exam preparation. A user registers, fills their own
knowledge-base sections with plain text, selects one or more sections, picks a task
type (technical / behavioral / mixed), and the AI generates questions, accepts
answers, and scores them with feedback. Each user's data is private.

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
| Deploy backend | **Render** / Railway / Fly.io (free) | Free tier |
| Deploy frontend | **Vercel** / Netlify / Cloudflare Pages | Free |

**Task types** (user choice): `technical`, `behavioral`, `mixed`.

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
│   │   │   ├── generate.py    # question generation
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
- [ ] `ai/generate.py`: `generate_questions(sections, mode, count)`
  - [ ] Gather content of the **current user's** selected sections
  - [ ] Apply a token budget: truncate/limit content so the prompt can't overflow
  - [ ] System prompt sets interviewer role; ask for **strict JSON** array of `{question, category}`
- [ ] Safe JSON parsing (strip ```json fences, try/except, one retry on parse fail)
- [ ] `POST /ai/generate` (protected): input `section_ids[]`, `mode`, `count`
  - [ ] Validate all sections belong to the user
  - [ ] Cap `count` (e.g. max 20) to control cost
- [ ] Mode logic: technical / behavioral / mixed (~50/50)

### Tests
- [ ] With mocked AI returning valid JSON -> parsed list of questions
- [ ] Mocked AI returning JSON wrapped in prose/fences -> still parsed
- [ ] Requesting another user's section -> 403/404
- [ ] `count` over the cap -> 422

### Definition of Done
- For a real section + `technical`, questions are relevant (manual check)
- Parser handles messy model output
- All checkboxes `[x]`, `pytest` green

---

## Phase 6 — Answer evaluation

**Goal:** AI scores the user's answer and gives feedback.

### Subtasks
- [ ] `ai/evaluate.py`: `evaluate_answer(question, answer, context)`
  - [ ] Returns **strict JSON**: `{score: 0-10, feedback, strengths[], gaps[]}`
  - [ ] Use low temperature (0 or near-0) for more consistent scoring
- [ ] Criteria in prompt tied to question type (technical -> accuracy/depth;
      behavioral -> STAR structure)
- [ ] `POST /ai/evaluate` (protected): `question`, `answer`, `section_ids[]`
- [ ] Clamp/validate score to 0–10; handle non-numeric model output

### Tests
- [ ] Mocked weak answer -> low score + non-empty `gaps`
- [ ] Mocked strong answer -> high score + non-empty `strengths`
- [ ] Score always coerced into 0–10 integer

### Definition of Done
- Manual check: weak vs strong answers get sensibly different scores
- All checkboxes `[x]`, `pytest` green

---

## Phase 7 — Sessions & persistence (user-scoped)

**Goal:** persist each user's training run and history.

### Subtasks
- [ ] `Session` model: `id`, `user_id (FK)`, `mode`, `section_ids`, `started_at`, `finished_at`
- [ ] `Attempt` model: `id`, `session_id (FK)`, `question`, `category`, `answer`,
      `score`, `feedback`, `created_at`
- [ ] Alembic migration
- [ ] `routers/sessions.py` (all under `get_current_user`):
  - [ ] `POST /sessions` — start a session
  - [ ] `POST /sessions/{id}/next` — next question
  - [ ] `POST /sessions/{id}/answer` — answer -> evaluate -> store
  - [ ] `GET /sessions/{id}` — session summary
  - [ ] `GET /sessions` — own session history (paginated)
- [ ] Prevent duplicate scoring on double-submit (idempotency per attempt)

### Tests
- [ ] Full cycle (mocked AI): start -> next -> answer -> stored attempt with score
- [ ] User sees only their own sessions
- [ ] Double-submitting the same answer doesn't double-score

### Definition of Done
- Full loop works via `/docs`: login -> start -> question -> answer -> score -> summary
- History is user-isolated
- All checkboxes `[x]`, `pytest` green

---

## Phase 8 — Frontend (React + Vite)

**Goal:** make it usable in the browser, with login.

### Subtasks
- [ ] `npm create vite@latest frontend -- --template react`
- [ ] Configure dev proxy to backend
- [ ] Auth context: store JWT, send `Authorization` header, handle 401 -> logout
- [ ] **Login / Register** screen
- [ ] **Sections** screen: list own sections, create, plain-text editor to fill content
- [ ] **Start training** screen: section checkboxes + mode selector
- [ ] **Training** screen: chat-like flow — question -> answer input -> score/feedback -> next
  - [ ] Loading states while AI is working (calls take seconds)
- [ ] **Summary** screen: questions, scores, average
- [ ] State via React state/context (no extra libs needed)

### Tests
- [ ] Light smoke tests (Vitest) for auth context and one screen render (optional)

### Definition of Done
- End-to-end in browser: register -> login -> fill a section with text -> train ->
  scores -> summary
- Logged-out user cannot reach protected screens
- All checkboxes `[x]`

---

## Phase 9 — Polish (iterative, one at a time)

- [ ] Streaming responses (tokens appear progressively)
- [ ] Progress stats: score chart, "weakest topics"
- [ ] Knowledge-base import: upload `.md`/`.txt` into a section
- [ ] Refresh tokens (longer sessions without re-login)
- [ ] Per-user rate limiting on AI endpoints (cost/abuse control)
- [ ] RAG (embeddings + vector search) if the knowledge base outgrows the token budget

---

## Phase 10 — Deploy

**Goal:** runs on the internet, for free.

### Subtasks
- [ ] DB: create free Postgres on Neon; get connection string
- [ ] Backend: switch `DATABASE_URL` to Postgres; run Alembic migrations on deploy
- [ ] Deploy backend to Render; secrets in platform env (not in code)
- [ ] Deploy frontend to Vercel; set backend URL
- [ ] Configure CORS to allow the frontend domain

### Definition of Done
- Full flow works on production URLs
- No secrets in the repo
- Migrations applied in prod

---

## Phase checklist

- [x] Phase 1 — Backend skeleton + /health
- [x] Phase 2 — Auth + users (JWT, Alembic)
- [x] Phase 3 — Knowledge base + plain-text editing (user-scoped)
- [x] Phase 4 — OpenRouter connection (mockable)
- [ ] Phase 5 — Question generation
- [ ] Phase 6 — Answer evaluation
- [ ] Phase 7 — Sessions + persistence (user-scoped)
- [ ] Phase 8 — React frontend with login
- [ ] Phase 9 — Polish
- [ ] Phase 10 — Deploy

**Rule:** do not advance until every subtask in the current phase is `[x]` and the
test suite is green.
