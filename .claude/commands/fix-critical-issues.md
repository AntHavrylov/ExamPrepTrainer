---
name: fix-critical-issues
description: Fix the critical (fix-first) issues identified in docs/review.md — crash on empty AI response, duplicate-attempt/duplicate-score races, and missing auth rate limiting / timing leak.
---

# Context

`docs/review.md` (2026-07-01 full-codebase review) flagged 15 findings. This
task covers only the "Fix first" priority group — the issues most likely to
crash a request or corrupt session/scoring data in production. Read
`docs/review.md` in full before starting; it has file/line references and
failure scenarios for each item below.

# Goal

Close the fix-first findings without changing behavior for the non-buggy
path. Each subtask should be a minimal, targeted fix — not a rewrite of the
surrounding code.

# Subtasks

## 1. Crash on empty AI response
- [ ] In `backend/app/ai/generate.py` (`generate_questions` /
      `generate_quiz_questions`, ~lines 73-98 and 135-176), treat a
      successfully-parsed but empty (`[]`) array as a failure and raise
      `AIClientError`, not a success.
- [ ] In `backend/app/routers/sessions.py:404`, remove the now-unreachable
      bare `new_rows[0]` crash risk — confirm the guard above makes this line
      safe, or add an explicit empty-check with a clear `HTTPException` if
      you want defense in depth.
- [ ] Add/adjust a test that feeds an empty-array AI response through
      `generate_batch` / `next_question` and asserts a clean 503
      (`AIClientError` → `HTTPException`) instead of a 500.

## 2. AI response count validation
- [ ] In the same parsers (`backend/app/ai/generate.py`), validate that the
      returned array length matches the requested `count`; raise
      `AIClientError` on mismatch (or truncate with a logged warning if a
      partial result is acceptable — confirm which behavior with the user
      before choosing).
- [ ] Add a test covering a short/truncated AI response.

## 3. Duplicate-attempt race (`POST /sessions/{id}/next`)
- [ ] In `backend/app/routers/sessions.py` (~lines 317-322, 401-424), close
      the TOCTOU window between reading `existing_count` and inserting the
      `Attempt`. Prefer a DB-level guard (unique constraint on
      `(session_id, question_bank_id)` or `(session_id, ordinal)`, or a
      `SELECT ... FOR UPDATE` on the session row) over an in-process lock,
      since the app may run multiple workers.
- [ ] Confirm `_session_plans[session.id][existing_count]` indexing can no
      longer serve the same bank question twice under concurrent requests.
- [ ] Add a test that fires two concurrent `next` requests for the same
      session and asserts only one `Attempt` is created.

## 4. Duplicate-score race (`answer` / `answer_stream`)
- [ ] In `backend/app/routers/sessions.py` (~lines 478-479, 589-592), make
      the `attempt.score is not None` check race-safe — e.g. a conditional
      `UPDATE ... WHERE score IS NULL` (checking rowcount) instead of a
      read-then-write, or row-level locking before the check.
- [ ] Confirm `qb.correct_answer_count` can no longer be double-incremented
      by concurrent submissions for the same attempt.
- [ ] Add a test that fires two concurrent submissions for the same attempt
      and asserts the score/evaluation call happens exactly once.

## 5. Auth rate limiting + timing leak
- [ ] Wire `check_ai_rate_limit` (or a dedicated limiter with its own
      threshold) into `POST /auth/login` and `POST /auth/register` in
      `backend/app/routers/auth.py`, keyed by IP and/or email.
- [ ] Fix the timing side-channel at `backend/app/routers/auth.py:75`: always
      run `verify_password` (against a dummy hash when the user doesn't
      exist) so response time doesn't reveal account existence.
- [ ] Add a test asserting repeated failed logins beyond the threshold return
      429, and that login timing for a nonexistent vs. existing email is not
      trivially distinguishable (or at minimum, that the dummy-hash path is
      exercised).

# Explicitly out of scope for this task

These are lower-priority findings from the same review — do not fix them
here unless asked:
- `backend/app/auth/deps.py:33` malformed-token 500 (fix-soon, not fix-first)
- Frontend findings (#10-#15 in `docs/review.md`)
- In-memory `_jobs` / `_session_plans` / rate-limiter state not surviving
  horizontal scaling (#5, #9) — architectural, needs its own design pass
- Token storage in `localStorage` (#15) — design tradeoff, not a bug fix

# Success criteria

- [ ] All 5 subtask groups above are checked off.
- [ ] `pytest` (backend) passes, including the new/updated tests for each
      fix.
- [ ] Manually verified: an AI call returning `[]` no longer 500s (returns a
      503 with a clear error).
- [ ] Manually or test-verified: two concurrent `next` calls on one session
      never produce more attempts than `target_question_count`.
- [ ] Manually or test-verified: two concurrent answer submissions for one
      attempt never double-count `correct_answer_count`.
- [ ] `/auth/login` and `/auth/register` return 429 after repeated rapid
      requests from the same client.
- [ ] No regression in the existing happy-path flows (session creation,
      answering, question-bank generation) — run the existing test suite plus
      a manual smoke test via `/verify` or `/run`.

# Approach

Work through the subtasks in order (1-5); 1 and 2 share the same file and are
naturally done together. For the two race conditions (3, 4), prefer a
database-level fix (constraint or locking read) over application-level
locks, since `docs/review.md` notes this app may later run multiple workers.
After each subtask, run the relevant backend tests before moving to the next.
