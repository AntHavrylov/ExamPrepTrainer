# Exam Prep Trainer

An AI-powered web app for interview and exam preparation. Users build their own
knowledge-base sections (plain text or uploaded `.md`/`.txt`), pick a task type
(technical / behavioral / mixed) and a training format (open-ended Q&A or
multiple-choice quiz), and the AI generates questions, accepts answers, and
scores them with feedback — all scoped to that user's own data.

Built end-to-end (backend, frontend, infra) as a portfolio project to
demonstrate practical AI-application engineering: prompt-driven generation and
grading, streaming responses, context-window management, auth, and
containerized deploys.

## Features

- **Knowledge base** — create sections, add text or upload `.md`/`.txt` files
- **AI question generation** — technical / behavioral / mixed, open-ended or
  multiple-choice, scoped to one or more sections
- **AI answer evaluation** — open-ended answers are scored and given feedback,
  streamed token-by-token over SSE; quiz answers are graded server-side with
  no AI call needed
- **Lightweight RAG** — when section content exceeds the model's context
  budget, chunks are ranked by keyword relevance instead of pulling in
  embeddings + a vector DB
- **Bring-your-own API key** — users can optionally supply their own
  OpenRouter key and pick a model, falling back to the app's default
- **Progress tracking** — score history and "weakest topics" over time
- **Auth** — JWT access + refresh tokens, per-user data isolation
- **Per-user rate limiting** on AI endpoints (cost/abuse control)
- **Light/dark theme**
- **Dockerized** — one command brings up Postgres + backend + frontend
  together, mirroring the production setup

## Stack

| Layer | Choice |
|-------|--------|
| Backend | Python, FastAPI, SQLAlchemy 2.x, Alembic |
| Frontend | React + Vite |
| Auth | JWT (passlib/bcrypt) |
| AI | OpenRouter (OpenAI-compatible API) |
| DB | SQLite (local) / Postgres (Docker, prod) |
| Tests | pytest + httpx (backend), Vitest + React Testing Library (frontend) |

See [`docs/Plan.md`](docs/Plan.md) for the full phased build plan.

## Running locally

### Option A — Docker (closest to production)

```bash
cp backend/.env.example backend/.env   # fill in SECRET_KEY / API_KEY_ENCRYPTION_KEY
docker compose up --build
```

- Frontend: http://localhost:8080
- Backend: http://localhost:8000 (proxied through Nginx at :8080 too)

### Option B — Run backend and frontend directly

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in SECRET_KEY / API_KEY_ENCRYPTION_KEY
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Generate the required secrets with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"                              # SECRET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # API_KEY_ENCRYPTION_KEY
```

An OpenRouter API key (set via the app's Settings screen, or as a server-side
default) is needed for AI features; OpenRouter has free-tier models.

## Tests

```bash
cd backend && pytest
cd frontend && npm test
```

## Project structure

```
backend/   FastAPI app, SQLAlchemy models, Alembic migrations, pytest suite
frontend/  React + Vite SPA
docs/      Build plan, phased checklist
```
