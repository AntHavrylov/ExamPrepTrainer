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
- [x] In `backend/app/ai/generate.py` (`_parse_questions` / `_parse_quiz_questions`),
      an empty (`[]`) array is now treated as a parse failure, not success -
      `generate_questions`/`generate_quiz_questions` raise `AIClientError`
      after the existing one-retry logic if both attempts come back empty.
- [x] `backend/app/routers/sessions.py:404` (now ~411): added an explicit
      `if not new_rows: raise HTTPException(503, ...)` guard as defense in
      depth, since the upstream fix makes this path unreachable in practice.
- [x] Added `test_generate_treats_empty_array_as_failure_and_retries` and
      `test_generate_fails_gracefully_when_empty_array_on_both_attempts` in
      `backend/tests/test_generate.py`.

## 2. AI response count validation
- [x] Investigated and **deliberately not implemented** as a hard
      retry/error: `backend/tests/test_question_bank.py::test_next_question_replenishes_pool_in_background_once_it_runs_dry`
      documents that a short (fewer-than-requested) response from the AI is
      expected, accepted behavior for background pool top-ups - retrying or
      erroring on undercount would burn an extra AI call on an already-known
      case and broke that existing test. The crash risk (empty response) is
      fully covered by #1; undercount alone was never a crash, just a softer
      finding. Left as-is; see `test_generate_questions_accepts_short_response_without_retrying`
      for the now-documented intended behavior.
- [x] No test needed beyond the one above (no behavior changed here).

## 3. Duplicate-attempt race (`POST /sessions/{id}/next`)
- [x] `_get_owned_session` now takes a `for_update` flag; `next_question`
      fetches the session with `with_for_update=True` before reading
      `existing_count`, serializing concurrent `next` calls for the same
      session on Postgres (real prod DB per `docker-compose.yml`). No-op on
      SQLite (used by the test suite) since SQLite doesn't support row
      locks - confirmed by inspecting compiled SQL.
- [x] The `_session_plans[session.id][existing_count]` read happens after
      the lock is acquired, so it's covered by the same serialization.
- [x] Added two tests in `backend/tests/test_sessions.py`:
      `test_next_question_lock_sees_concurrently_committed_attempt` (a
      deterministic, non-threaded simulation using two real DB sessions,
      proving the locked re-read sees a concurrently committed attempt -
      true blocking-under-concurrency can't be exercised against SQLite,
      a no-op there), and `test_next_question_route_requests_the_session_lock`
      (a monkeypatch spy proving the live `/sessions/{id}/next` route itself
      passes `for_update=True` - added after a recheck found the first test
      alone would NOT catch a regression where the route stopped requesting
      the lock, since it exercises the helper directly with a hardcoded
      `True` rather than going through the route).

## 4. Duplicate-score race (`answer` / `answer_stream`)
- [x] Added `_lock_attempt()` helper (`db.get(..., with_for_update=True,
      populate_existing=True)`) and call it right before writing a score in
      `answer` (both quiz and open-ended branches) and in `answer_stream`'s
      `event_stream()` write section - re-checks `score is not None` under
      the lock immediately before writing, after the (potentially slow) AI
      call has already completed.
- [x] `qb.correct_answer_count` increments now also lock the `QuestionBank`
      row (`with_for_update=True`) to close a related lost-update race
      between two *different* attempts on the same bank question.
- [x] Added `test_lock_attempt_reflects_concurrent_commit_and_prevents_double_score`
      (deterministic two-session simulation, same approach as #3) plus three
      wiring tests - `test_answer_quiz_route_acquires_attempt_lock`,
      `test_answer_open_ended_route_acquires_attempt_lock`,
      `test_answer_stream_route_acquires_attempt_lock` - added after a
      recheck confirmed the existing `test_double_submit_does_not_double_*`
      tests only exercise the earlier *unlocked* fast-path check and kept
      passing even with `_lock_attempt` deleted from all three call sites;
      the new spy-based tests fail immediately if any call site is removed.

## 5. Auth rate limiting + timing leak
- [x] Added `check_auth_rate_limit`/`enforce_auth_rate_limit` (keyed by
      client IP, not email, to avoid a new victim-lockout vector) in
      `backend/app/rate_limit.py`, wired into `POST /auth/login` and
      `POST /auth/register` via new `auth_rate_limit_max_requests`/
      `auth_rate_limit_window_seconds` settings (default 10/60s).
- [x] Added `DUMMY_PASSWORD_HASH` in `backend/app/auth/security.py`; `login`
      now always calls `verify_password` (against the dummy hash when the
      user doesn't exist) so response timing doesn't reveal account
      existence.
- [x] Added `test_login_is_rate_limited_per_ip`, `test_register_is_rate_limited_per_ip`,
      and `test_login_verifies_password_hash_even_for_unknown_email` in
      `backend/tests/test_auth.py`, plus unit tests for the new limiter in
      `backend/tests/test_rate_limit.py`. Added an autouse fixture in
      `conftest.py` to reset the new rate-limit bucket between tests.

# Explicitly out of scope for this task

These are lower-priority findings from the same review — do not fix them
here unless asked:
- `backend/app/auth/deps.py:33` malformed-token 500 (fix-soon, not fix-first)
- Frontend findings (#10-#15 in `docs/review.md`)
- In-memory `_jobs` / `_session_plans` / rate-limiter state not surviving
  horizontal scaling (#5, #9) — architectural, needs its own design pass
- Token storage in `localStorage` (#15) — design tradeoff, not a bug fix

# Success criteria

- [x] All 5 subtask groups above are checked off (#2 resolved as
      "investigated, intentionally not changed" — see notes above).
- [x] `pytest` (backend) passes: 190 passed / 1 pre-existing failure
      (`test_client_retries_on_429_then_succeeds`, an unrelated OpenRouter
      429-retry timing bug present before this task started — confirmed via
      baseline run, and reconfirmed during a later recheck pass).
- [x] Verified via test: an AI call returning `[]` no longer 500s (returns a
      503 with a clear error) — see `test_generate_fails_gracefully_when_empty_array_on_both_attempts`.
- [x] Test-verified (see #3 above): the locking mechanism `next_question`
      relies on correctly serializes concurrent attempt creation, AND the
      live route actually invokes it (not just the helper in isolation).
- [x] Test-verified (see #4 above): the locking mechanism `answer`/
      `answer_stream` relies on correctly prevents a double-score write, AND
      all three call sites (quiz, open-ended, streaming) actually invoke it.
- [x] `/auth/login` and `/auth/register` return 429 after repeated rapid
      requests from the same client — see `test_login_is_rate_limited_per_ip`,
      `test_register_is_rate_limited_per_ip`.
- [x] No regression in existing happy-path flows — full backend suite passes
      (176 → 190 tests as new coverage was added, only the pre-existing
      unrelated failure remains). No live docker/manual smoke test was run as
      part of this task (backend-only change, no frontend touched); recommend
      a manual `/verify` pass before deploying to production given the
      concurrency-sensitive changes.

# Recheck notes (post-completion audit)

A follow-up recheck (after the initial pass above) found and closed two real
test-coverage gaps, and also surfaced/recovered from an operator error:

- An intermediate verification step accidentally ran `git checkout --` on
  `backend/app/routers/sessions.py`, which discarded all of that file's
  uncommitted fixes (#1's defensive guard, #3, #4). Caught immediately by a
  `git diff --stat` check showing an empty diff; the fix was fully
  reconstructed from a diff captured earlier in the session and reverified
  byte-for-byte (`+78/-28` lines, matching the pre-revert diff exactly) and
  by rerunning the full test suite.
- `test_next_question_lock_sees_concurrently_committed_attempt` (#3) and
  `test_lock_attempt_reflects_concurrent_commit_and_prevents_double_score`
  (#4) call the `_get_owned_session`/`_lock_attempt` helpers directly with a
  hardcoded `for_update=True`/lock call - proven (by deliberately removing
  `for_update=True` from the `next_question` route and rerunning the suite)
  to NOT catch a regression where the *route* stops requesting the lock.
  Added `test_next_question_route_requests_the_session_lock` and three
  `test_answer_*_route_acquires_attempt_lock` tests that spy on the actual
  route code path; confirmed each fails when its corresponding lock call is
  removed from the route, and passes against the real fix.

# Approach

Work through the subtasks in order (1-5); 1 and 2 share the same file and are
naturally done together. For the two race conditions (3, 4), prefer a
database-level fix (constraint or locking read) over application-level
locks, since `docs/review.md` notes this app may later run multiple workers.
After each subtask, run the relevant backend tests before moving to the next.
