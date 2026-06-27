import json
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.ai.client import AIClientError, MissingApiKeyError, get_ai_client
from app.ai.context import build_context
from app.ai.evaluate import evaluate_answer, evaluate_answer_stream
from app.ai.provider import AIProvider
from app.auth.deps import get_current_user
from app.config import settings
from app.db import get_db, get_session_factory
from app.models import Attempt, Section, User
from app.models import Session as TrainingSession
from app.question_pool import (
    bank_rows_from_batch,
    generate_batch,
    matching_bank_rows,
    schedule_replenish_if_low,
    scope_key,
)
from app.rate_limit import check_ai_rate_limit, enforce_ai_rate_limit
from app.schemas import (
    AnswerRequest,
    AnswerResultRead,
    AttemptSummaryRead,
    NextQuestionRead,
    ScorePoint,
    SessionRead,
    SessionSummaryRead,
    StartSessionRequest,
    StatsRead,
    TopicStat,
)
from app.section_access import get_owned_sections

router = APIRouter(prefix="/sessions", tags=["sessions"])

_QUIZ_CORRECT_FEEDBACK = {
    "en": "Correct!",
    "uk": "Правильно!",
    "ru": "Правильно!",
}

_QUIZ_INCORRECT_FEEDBACK_TEMPLATES = {
    "en": "Incorrect. The correct answer was: {answer}",
    "uk": "Неправильно. Правильна відповідь: {answer}",
    "ru": "Неправильно. Правильный ответ: {answer}",
}


def _quiz_feedback(language: str, is_correct: bool, correct_option: str) -> str:
    if is_correct:
        return _QUIZ_CORRECT_FEEDBACK.get(language, _QUIZ_CORRECT_FEEDBACK["en"])
    template = _QUIZ_INCORRECT_FEEDBACK_TEMPLATES.get(language, _QUIZ_INCORRECT_FEEDBACK_TEMPLATES["en"])
    return template.format(answer=correct_option)


def _get_owned_session(db: DBSession, session_id: int, user_id: int) -> TrainingSession:
    session = db.get(TrainingSession, session_id)
    if session is None or session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def _latest_attempt(db: DBSession, session_id: int) -> Attempt | None:
    return db.scalar(
        select(Attempt).where(Attempt.session_id == session_id).order_by(Attempt.id.desc())
    )


def _attempt_count(db: DBSession, session_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Attempt).where(Attempt.session_id == session_id)) or 0


def _attempt_to_result(
    attempt: Attempt,
    strengths: list[str] | None = None,
    gaps: list[str] | None = None,
    feedback: str | None = None,
) -> AnswerResultRead:
    if attempt.format == "quiz":
        return AnswerResultRead(
            attempt_id=attempt.id,
            format=attempt.format,
            score=attempt.score,
            feedback=attempt.feedback,
            correct_index=attempt.correct_index,
            is_correct=attempt.selected_index == attempt.correct_index,
            explanation=attempt.explanation,
        )
    return AnswerResultRead(
        attempt_id=attempt.id,
        format=attempt.format,
        score=attempt.score,
        feedback=feedback if feedback is not None else attempt.feedback,
        strengths=strengths or [],
        gaps=gaps or [],
        explanation=attempt.explanation,
    )


def _attempt_to_summary(attempt: Attempt) -> AttemptSummaryRead:
    answered = attempt.score is not None
    return AttemptSummaryRead(
        id=attempt.id,
        question=attempt.question,
        category=attempt.category,
        format=attempt.format,
        options=attempt.options,
        selected_index=attempt.selected_index if answered else None,
        correct_index=attempt.correct_index if answered else None,
        answer=attempt.answer,
        score=attempt.score,
        feedback=attempt.feedback,
        created_at=attempt.created_at,
        hint=attempt.hint,
        explanation=attempt.explanation if answered else None,
    )


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def start_session(
    payload: StartSessionRequest,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ai_client: AIProvider = Depends(get_ai_client),
    session_factory=Depends(get_session_factory),
) -> TrainingSession:
    get_owned_sections(db, payload.section_ids, current_user.id)

    # The pool is keyed by language too (a question generated in one language is
    # useless for a session running in another), and that language comes from
    # the user's current setting rather than this request - so a combination
    # that looks fully stocked in the Question Bank can still be empty for the
    # active language. Check up front, using the exact same matching the session
    # itself will use, so we never create a session that's doomed to fail on its
    # first question with a confusing mid-session error.
    scope = scope_key(payload.section_ids)
    matching = matching_bank_rows(
        db, current_user.id, payload.mode, payload.format, payload.difficulty,
        current_user.language, scope, section_mode=payload.section_mode,
    )
    unused = sum(1 for row in matching if row.used_at is None)

    if len(matching) == 0 and not settings.live_question_generation_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "no_questions",
                "message": (
                    "No questions available for this combination. "
                    "Generate some from the Question Bank tab first."
                ),
                "mode": payload.mode,
                "format": payload.format,
                "difficulty": payload.difficulty,
                "language": current_user.language,
            },
        )

    session = TrainingSession(
        user_id=current_user.id,
        mode=payload.mode,
        format=payload.format,
        difficulty=payload.difficulty,
        target_question_count=payload.count or current_user.session_length,
        section_ids=payload.section_ids,
        section_mode=payload.section_mode,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    if settings.live_question_generation_enabled:
        # Pre-warm the pool only if it's genuinely empty (e.g. the very first
        # session ever for this exact mode/format/difficulty/language/sections
        # combination) - if anything is already sitting there unused, the user's
        # first click is already covered and there's nothing to gain.
        schedule_replenish_if_low(
            background_tasks,
            matching,
            unused,
            current_user.id,
            payload.mode,
            payload.format,
            payload.difficulty,
            current_user.language,
            scope,
            payload.section_ids,
            payload.section_mode,
            ai_client,
            session_factory,
        )

    return session


@router.post("/{session_id}/finish", response_model=SessionRead)
def finish_session(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrainingSession:
    session = _get_owned_session(db, session_id, current_user.id)
    if session.finished_at is None:
        session.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(session)
    return session


@router.post("/{session_id}/next", response_model=NextQuestionRead)
async def next_question(
    session_id: int,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(enforce_ai_rate_limit),
    ai_client: AIProvider = Depends(get_ai_client),
    session_factory=Depends(get_session_factory),
) -> NextQuestionRead:
    session = _get_owned_session(db, session_id, current_user.id)
    if session.finished_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Session has already been finished"
        )

    existing_count = _attempt_count(db, session.id)
    if existing_count >= session.target_question_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session already has the configured number of questions",
        )
    scope = scope_key(session.section_ids)

    matching = matching_bank_rows(
        db, current_user.id, session.mode, session.format, session.difficulty,
        current_user.language, scope, section_mode=session.section_mode,
    )
    candidate = next((row for row in matching if row.used_at is None), None)
    if candidate is None and matching:
        # All questions have been seen — recycle, starting with the oldest.
        candidate = min(matching, key=lambda r: r.used_at)

    if candidate is None:
        if not settings.live_question_generation_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "No questions available for this combination. "
                    "Generate some from the Question Bank tab first."
                ),
            )
        sections = get_owned_sections(db, session.section_ids, current_user.id)
        avoid_themes = [row.theme for row in matching]
        try:
            # For "or" multi-section sessions generate per section so every bank
            # row carries a single-section scope and can be attributed correctly
            # in stats.  For "and" sessions the combined scope is intentional.
            if session.section_mode == "or" and len(sections) > 1:
                section_map = {s.id: s for s in sections}
                per_section_count = max(1, settings.question_bank_batch_size // len(sections))
                new_rows = []
                for sid in session.section_ids:
                    sec_scope = scope_key([sid])
                    sec_avoid = [row.theme for row in matching if set(row.section_ids) == {sid}]
                    batch = await generate_batch(
                        [section_map[sid]],
                        session.mode,
                        session.format,
                        per_section_count,
                        ai_client,
                        difficulty=session.difficulty,
                        avoid_themes=sec_avoid,
                        language=current_user.language,
                    )
                    new_rows += bank_rows_from_batch(
                        batch, current_user.id, session.mode, session.format, session.difficulty,
                        current_user.language, sec_scope,
                    )
            else:
                generated_batch = await generate_batch(
                    sections,
                    session.mode,
                    session.format,
                    settings.question_bank_batch_size,
                    ai_client,
                    difficulty=session.difficulty,
                    avoid_themes=avoid_themes,
                    language=current_user.language,
                )
                new_rows = bank_rows_from_batch(
                    generated_batch, current_user.id, session.mode, session.format, session.difficulty,
                    current_user.language, scope,
                )
        except MissingApiKeyError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
        except AIClientError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
        db.add_all(new_rows)
        db.flush()
        matching = matching + new_rows
        candidate = new_rows[0]

    candidate.used_at = datetime.now(timezone.utc)
    unused_after = sum(1 for row in matching if row.used_at is None)
    attempt = Attempt(
        session_id=session.id,
        question=candidate.question,
        category=candidate.category,
        format=session.format,
        options=candidate.options,
        correct_index=candidate.correct_index,
        hint=candidate.hint,
        explanation=candidate.explanation,
        section_ids=candidate.section_ids,
    )

    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    if settings.live_question_generation_enabled:
        # The pool just ran out (or is about to next time) - top it up quietly in
        # the background so the next click usually doesn't have to wait on (or
        # risk failing) a live generation call.
        schedule_replenish_if_low(
            background_tasks,
            matching,
            unused_after,
            current_user.id,
            session.mode,
            session.format,
            session.difficulty,
            current_user.language,
            scope,
            session.section_ids,
            session.section_mode,
            ai_client,
            session_factory,
        )

    return NextQuestionRead(
        attempt_id=attempt.id,
        question=attempt.question,
        category=attempt.category,
        options=attempt.options,
        hint=attempt.hint,
        question_number=existing_count + 1,
        total_questions=session.target_question_count,
    )


@router.post("/{session_id}/answer", response_model=AnswerResultRead)
async def answer(
    session_id: int,
    payload: AnswerRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ai_client: AIProvider = Depends(get_ai_client),
) -> AnswerResultRead:
    session = _get_owned_session(db, session_id, current_user.id)

    attempt = _latest_attempt(db, session.id)
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No pending question for this session"
        )

    if attempt.score is not None:
        return _attempt_to_result(attempt)

    if session.finished_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Session has already been finished"
        )

    if attempt.format == "quiz":
        if payload.selected_index is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="selected_index is required for quiz answers",
            )
        if payload.selected_index >= len(attempt.options):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="selected_index out of range",
            )

        attempt.selected_index = payload.selected_index
        is_correct = payload.selected_index == attempt.correct_index
        attempt.score = 10 if is_correct else 0
        attempt.feedback = _quiz_feedback(
            current_user.language, is_correct, attempt.options[attempt.correct_index]
        )
        db.commit()
        db.refresh(attempt)
        return _attempt_to_result(attempt)

    if not payload.answer:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="answer is required for open-ended answers",
        )

    check_ai_rate_limit(current_user.id)

    sections = get_owned_sections(db, session.section_ids, current_user.id)
    context = build_context(
        sections, settings.max_generation_context_chars, query=f"{attempt.question} {payload.answer}"
    )

    try:
        evaluation = await evaluate_answer(
            attempt.question, payload.answer, context, ai_client, language=current_user.language
        )
    except MissingApiKeyError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except AIClientError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    stored_feedback = evaluation["feedback"]
    if evaluation["strengths"]:
        stored_feedback += "\n\nStrengths: " + "; ".join(evaluation["strengths"])
    if evaluation["gaps"]:
        stored_feedback += "\nGaps: " + "; ".join(evaluation["gaps"])

    attempt.answer = payload.answer
    attempt.score = evaluation["score"]
    attempt.feedback = stored_feedback
    db.commit()
    db.refresh(attempt)

    return _attempt_to_result(
        attempt,
        strengths=evaluation["strengths"],
        gaps=evaluation["gaps"],
        feedback=evaluation["feedback"],
    )


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _sse_result_only(result: AnswerResultRead):
    yield _sse_event("result", result.model_dump())


@router.post("/{session_id}/answer/stream")
async def answer_stream(
    session_id: int,
    payload: AnswerRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ai_client: AIProvider = Depends(get_ai_client),
    session_factory=Depends(get_session_factory),
) -> StreamingResponse:
    session = _get_owned_session(db, session_id, current_user.id)

    attempt = _latest_attempt(db, session.id)
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No pending question for this session"
        )

    if attempt.format != "open_ended":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Streaming is only available for open-ended answers",
        )

    if attempt.score is not None:
        return StreamingResponse(
            _sse_result_only(_attempt_to_result(attempt)), media_type="text/event-stream"
        )

    if session.finished_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Session has already been finished"
        )

    if not payload.answer:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="answer is required for open-ended answers",
        )

    check_ai_rate_limit(current_user.id)

    sections = get_owned_sections(db, session.section_ids, current_user.id)
    context = build_context(
        sections, settings.max_generation_context_chars, query=f"{attempt.question} {payload.answer}"
    )

    attempt_id = attempt.id
    question = attempt.question
    answer_text = payload.answer
    language = current_user.language

    async def event_stream():
        evaluation = None
        try:
            async for delta, final_evaluation in evaluate_answer_stream(
                question, answer_text, context, ai_client, language=language
            ):
                if delta is not None:
                    yield _sse_event("delta", {"text": delta})
                if final_evaluation is not None:
                    evaluation = final_evaluation
        except AIClientError as exc:
            yield _sse_event("error", {"detail": str(exc)})
            return

        stream_db = session_factory()
        try:
            stored_attempt = stream_db.get(Attempt, attempt_id)
            stored_feedback = evaluation["feedback"]
            if evaluation["strengths"]:
                stored_feedback += "\n\nStrengths: " + "; ".join(evaluation["strengths"])
            if evaluation["gaps"]:
                stored_feedback += "\nGaps: " + "; ".join(evaluation["gaps"])

            stored_attempt.answer = answer_text
            stored_attempt.score = evaluation["score"]
            stored_attempt.feedback = stored_feedback
            stream_db.commit()
            stream_db.refresh(stored_attempt)
            db_result = _attempt_to_result(
                stored_attempt,
                strengths=evaluation["strengths"],
                gaps=evaluation["gaps"],
                feedback=evaluation["feedback"],
            )
        finally:
            stream_db.close()

        yield _sse_event("result", db_result.model_dump())

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/stats", response_model=StatsRead)
def get_stats(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StatsRead:
    sessions = list(
        db.scalars(select(TrainingSession).where(TrainingSession.user_id == current_user.id))
    )
    if not sessions:
        return StatsRead(total_attempts=0, average_score=None, score_history=[], weakest_topics=[])

    session_by_id = {session.id: session for session in sessions}
    attempts = list(
        db.scalars(
            select(Attempt)
            .where(Attempt.session_id.in_(session_by_id.keys()), Attempt.score.isnot(None))
            .order_by(Attempt.created_at)
        )
    )
    if not attempts:
        return StatsRead(total_attempts=0, average_score=None, score_history=[], weakest_topics=[])

    # Group scored attempts by session; each chart point = one session average.
    session_groups: dict[int, list[Attempt]] = defaultdict(list)
    for attempt in attempts:
        session_groups[attempt.session_id].append(attempt)

    # Collect every section referenced by sessions that have scored attempts.
    all_section_ids: set[int] = set()
    for sid in session_groups:
        if sid in session_by_id:
            all_section_ids.update(session_by_id[sid].section_ids)

    section_names: dict[int, str] = {
        section.id: section.name
        for section in db.scalars(select(Section).where(Section.id.in_(all_section_ids)))
    }

    # Build per-session score history with accurate per-section scores.
    # An attempt is attributed to a section only when the bank row it came from
    # was generated for that single section (section_ids length == 1).  Questions
    # generated for a combined scope (e.g. [A, B]) cannot be split, so they only
    # contribute to the overall session score, not to individual section scores.
    def _attempt_sec_ids(attempt: Attempt, session: TrainingSession) -> list[int]:
        return attempt.section_ids if attempt.section_ids is not None else session.section_ids

    def _section_scores_for_group(grp: list[Attempt], session: TrainingSession) -> dict[int, float]:
        per_section: dict[int, list[int]] = defaultdict(list)
        for attempt in grp:
            for sec_id in _attempt_sec_ids(attempt, session):
                if sec_id in section_names:
                    per_section[sec_id].append(attempt.score)
        return {
            sec_id: round(sum(scores) / len(scores), 1)
            for sec_id, scores in per_section.items()
        }

    score_history = sorted(
        [
            ScorePoint(
                session_id=sid,
                created_at=session_by_id[sid].started_at,
                score=round(sum(a.score for a in grp) / len(grp), 1),
                section_scores=_section_scores_for_group(grp, session_by_id[sid]),
            )
            for sid, grp in session_groups.items()
            if sid in session_by_id
        ],
        key=lambda p: (p.created_at, p.session_id),
    )

    average_score = sum(a.score for a in attempts) / len(attempts)

    topic_scores: dict[int, list[int]] = {}
    for attempt in attempts:
        for section_id in _attempt_sec_ids(attempt, session_by_id[attempt.session_id]):
            if section_id in section_names:
                topic_scores.setdefault(section_id, []).append(attempt.score)

    weakest_topics = sorted(
        [
            TopicStat(
                section_id=section_id,
                section_name=section_names[section_id],
                average_score=sum(scores) / len(scores),
                attempt_count=len(scores),
            )
            for section_id, scores in topic_scores.items()
        ],
        key=lambda topic: topic.average_score,
    )[:5]

    return StatsRead(
        total_attempts=len(attempts),
        average_score=average_score,
        score_history=score_history,
        weakest_topics=weakest_topics,
        section_names=section_names,
    )


@router.get("/{session_id}", response_model=SessionSummaryRead)
def get_session(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionSummaryRead:
    session = _get_owned_session(db, session_id, current_user.id)
    attempts = list(
        db.scalars(select(Attempt).where(Attempt.session_id == session.id).order_by(Attempt.id))
    )
    scored = [a.score for a in attempts if a.score is not None]
    average_score = sum(scored) / len(scored) if scored else None

    return SessionSummaryRead(
        id=session.id,
        mode=session.mode,
        format=session.format,
        difficulty=session.difficulty,
        target_question_count=session.target_question_count,
        section_ids=session.section_ids,
        section_mode=session.section_mode,
        started_at=session.started_at,
        finished_at=session.finished_at,
        attempts=[_attempt_to_summary(a) for a in attempts],
        average_score=average_score,
    )


@router.get("", response_model=list[SessionRead])
def list_sessions(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 20,
    offset: int = 0,
) -> list[TrainingSession]:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    return list(
        db.scalars(
            select(TrainingSession)
            .where(TrainingSession.user_id == current_user.id)
            .order_by(TrainingSession.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
