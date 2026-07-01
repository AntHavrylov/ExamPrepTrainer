# Code Review — 2026-07-01

Full-codebase review (no pending PR/diff — `main` was clean and in sync with
`origin/main`, so this covers the current state of `backend/app` and
`frontend/src`). Findings are ordered by severity within each section; each
includes a concrete trigger.

## Backend — correctness (business logic / AI pipeline)

1. **`backend/app/routers/sessions.py:404`** — `candidate = new_rows[0]`
   crashes with an unhandled `IndexError` when the AI legitimately returns
   `[]`. `generate_questions`/`generate_quiz_questions`
   (`backend/app/ai/generate.py:73-98, 135-176`) treat an empty array as a
   *successful* parse rather than raising `AIClientError`, so a model that
   returns zero items (safety filter, insufficient context) reaches this line
   and the endpoint 500s, with the empty insert already flushed on the
   session.

2. **`backend/app/routers/sessions.py:317-322` and `401-424`** — TOCTOU race
   on attempt creation. `existing_count` is read once, then (after a
   potentially slow live-generation `await`) an `Attempt` is inserted with no
   re-check. Two near-simultaneous `POST /sessions/{id}/next` calls (double
   click, client retry after a timeout) both pass the "not yet at target
   count" guard and both insert — the session ends up with more attempts than
   `target_question_count`, and in `section_mode == "or"` both requests index
   the same `_session_plans[session.id][existing_count]` entry, serving the
   identical bank question twice and double-incrementing `asked_count`.

3. **`backend/app/routers/sessions.py:478-479` and `589-592`** — same TOCTOU
   pattern on answer submission: `if attempt.score is not None: return` is
   only checked once, before any `await`. Two concurrent submissions for the
   same attempt (duplicate tab, retried request) both see `score is None`,
   both call the AI evaluator, and both commit a score — if both come back
   ≥7, `qb.correct_answer_count` is incremented twice for one real answer,
   permanently inflating the stat used later for pool re-ranking in
   `_sort_pool`.

4. **`backend/app/ai/generate.py:73-98, 135-176`** — the parsers never check
   that the returned array length matches the requested `count`. A short or
   empty response is accepted as "valid," so callers
   (`question_pool.py:100-116`, both `next_question` call sites) silently get
   fewer questions than requested, or zero — feeding straight into finding #1.

5. **`backend/app/generation_jobs.py:16` (`_jobs`) and
   `backend/app/routers/sessions.py:47` (`_session_plans`)** — both are
   process-local, unlocked in-memory dicts. Not a bug under the current
   single-container deploy (see `Deploy.txt`/`docker-compose.yml`, one
   backend process), but a latent scaling trap: the moment this runs with
   `uvicorn --workers >1` or is scaled to multiple containers, job-status
   polling can 404 for jobs owned by a different worker, and session plans
   get independently rebuilt per worker from a stale snapshot, risking
   duplicate/skipped questions.

## Backend — auth / security

6. **`backend/app/routers/auth.py:75`** — Login has a timing side-channel:
   `user is None or not verify_password(...)` short-circuits, so a
   nonexistent email returns almost instantly while a real one takes the
   full bcrypt verification time. An attacker can measure response latency
   across many emails to enumerate registered accounts.

7. **No rate limiting on `/auth/login` or `/auth/register`** — the only rate
   limiter (`backend/app/rate_limit.py`) is wired to AI endpoints via
   `enforce_ai_rate_limit`, not to auth. Combined with #6, this allows
   unlimited credential-stuffing/password-guessing or mass account creation
   with no throttling.

8. **`backend/app/auth/deps.py:33`** — `int(user_id)` runs *outside* the
   `try/except JWTError` block (lines 24-27). A token that passes signature
   and expiry checks but carries a non-numeric `sub` (crafted or legacy
   token) raises an uncaught `ValueError`, returning a raw 500 instead of a
   401.

9. **`backend/app/rate_limit.py:10`** — in-memory only, keyed per `user_id`,
   entries are never evicted (only individual timestamps are popped, the
   outer dict key persists forever). Since registration is open, this is an
   unbounded, low-severity memory-growth vector over the process lifetime.
   It has the same single-process limitation as finding #5: it does not hold
   under multiple workers/containers.

No IDOR issues found in `section_access.py` or `user_api_keys.py` (both
consistently scope by `user_id`); CORS config in `main.py`/`config.py` is
safe; `crypto.py`'s Fernet usage and JWT algorithm pinning
(`algorithms=[settings.algorithm]`) are correct; secrets are gitignored and
not in git history.

## Frontend

10. **`frontend/src/screens/TrainingScreen.jsx:73-93`** — the session-resume
    check (`attempts.length >= target_question_count`) runs before checking
    whether the last attempt was actually scored. If a user closes the tab on
    the final unanswered question and reopens the app, resume immediately
    calls `onFinish()`, silently dropping the last question instead of
    letting them answer it.

11. **`frontend/src/screens/TrainingScreen.jsx:37-43`** — `fetchNext()`
    blindly retries `api.nextQuestion(sessionId)` on any non-409 error, with
    no idempotency. If the first request actually succeeded server-side but
    the response was lost (network blip), the retry creates a second
    attempt, inflating `attempts.length` past `target_question_count` and
    interacting with the backend TOCTOU race (#2).

12. **`frontend/src/screens/TrainingScreen.jsx:129-144` +
    `frontend/src/api.js:243-272`** (`streamAnswer`) — the SSE-style
    streaming fetch has no `AbortController`. Navigating away or interrupting
    mid-stream leaves the `reader.read()` loop running, calling
    `setStreamingFeedback`/`setResult` on an unmounted component and keeping
    the connection to the LLM backend open.

13. **`frontend/src/screens/ProgressScreen.jsx:121-126` and
    `frontend/src/screens/SummaryScreen.jsx:21-26`** — both data-loading
    effects lack a cancellation guard (unlike `TrainingScreen`'s resume
    effect, which has one). Fast navigation away right after mount triggers
    a "set state on unmounted component" warning/leak.

14. **`frontend/src/screens/QuestionBankScreen.jsx:119-149`** — the
    job-polling effect schedules an async `setTimeout` callback; cleanup only
    calls `clearTimeout(id)`, which cannot cancel an already-in-flight
    `await Promise.allSettled(...)`. Navigating away mid-poll lets the
    resolved promise call `setActiveJobs`/`setGenSuccess`/`setGenError` after
    unmount.

15. **`frontend/src/context/AuthContext.jsx`, `frontend/src/api.js`** —
    access and refresh tokens are stored in plain `localStorage`, readable by
    any injected script. Worth flagging as a design tradeoff (not a one-line
    fix) given the refresh token's longer lifetime.

No other issues stood out in `LoginScreen`, `SectionsScreen`, `Sidebar`,
`LanguageContext`, or `useServerWakeup` — the latter's cold-start
retry/backoff and cleanup via `cancelledRef` is implemented correctly and is
a good pattern to reuse for findings #13/#14.

## Suggested priority

- Fix first: #1 (crash on empty AI response), #2/#3 (double-attempt /
  double-score races — same root cause, a missing DB-level uniqueness
  constraint or row lock would fix both), #6/#7 (auth has no rate limiting or
  timing-safe check).
- Fix soon: #4 (validate AI response count), #8 (auth crash on malformed
  token), #10/#11 (training resume/retry logic), #12/#14 (unmounted-component
  writes / dangling stream).
- Track for later: #5/#9 (in-memory state won't survive horizontal scaling),
  #13 (minor cleanup), #15 (token storage tradeoff).
