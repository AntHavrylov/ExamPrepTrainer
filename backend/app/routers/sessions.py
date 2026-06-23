import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.ai.client import AIClientError, OpenRouterClient, get_ai_client
from app.ai.context import build_context
from app.ai.evaluate import evaluate_answer, evaluate_answer_stream
from app.ai.generate import generate_questions, generate_quiz_questions
from app.auth.deps import get_current_user
from app.config import settings
from app.db import get_db, get_session_factory
from app.models import Attempt, Section, User
from app.models import Session as TrainingSession
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


def _get_owned_session(db: DBSession, session_id: int, user_id: int) -> TrainingSession:
    session = db.get(TrainingSession, session_id)
    if session is None or session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def _latest_attempt(db: DBSession, session_id: int) -> Attempt | None:
    return db.scalar(
        select(Attempt).where(Attempt.session_id == session_id).order_by(Attempt.id.desc())
    )


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
        )
    return AnswerResultRead(
        attempt_id=attempt.id,
        format=attempt.format,
        score=attempt.score,
        feedback=feedback if feedback is not None else attempt.feedback,
        strengths=strengths or [],
        gaps=gaps or [],
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
    )


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def start_session(
    payload: StartSessionRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrainingSession:
    get_owned_sections(db, payload.section_ids, current_user.id)

    session = TrainingSession(
        user_id=current_user.id,
        mode=payload.mode,
        format=payload.format,
        section_ids=payload.section_ids,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/{session_id}/next", response_model=NextQuestionRead)
async def next_question(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(enforce_ai_rate_limit),
    ai_client: OpenRouterClient = Depends(get_ai_client),
) -> NextQuestionRead:
    session = _get_owned_session(db, session_id, current_user.id)
    sections = get_owned_sections(db, session.section_ids, current_user.id)

    try:
        if session.format == "quiz":
            questions = await generate_quiz_questions(sections, session.mode, 1, ai_client)
            generated = questions[0]
            attempt = Attempt(
                session_id=session.id,
                question=generated["question"],
                category=generated["category"],
                format="quiz",
                options=generated["options"],
                correct_index=generated["correct_index"],
            )
        else:
            questions = await generate_questions(sections, session.mode, 1, ai_client)
            generated = questions[0]
            attempt = Attempt(
                session_id=session.id,
                question=generated["question"],
                category=generated["category"],
                format="open_ended",
            )
    except AIClientError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    return NextQuestionRead(
        attempt_id=attempt.id,
        question=attempt.question,
        category=attempt.category,
        options=attempt.options,
    )


@router.post("/{session_id}/answer", response_model=AnswerResultRead)
async def answer(
    session_id: int,
    payload: AnswerRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ai_client: OpenRouterClient = Depends(get_ai_client),
) -> AnswerResultRead:
    session = _get_owned_session(db, session_id, current_user.id)

    attempt = _latest_attempt(db, session.id)
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No pending question for this session"
        )

    if attempt.score is not None:
        return _attempt_to_result(attempt)

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
        attempt.feedback = (
            "Correct!"
            if is_correct
            else f"Incorrect. The correct answer was: {attempt.options[attempt.correct_index]}"
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
        evaluation = await evaluate_answer(attempt.question, payload.answer, context, ai_client)
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
    ai_client: OpenRouterClient = Depends(get_ai_client),
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

    async def event_stream():
        evaluation = None
        try:
            async for delta, final_evaluation in evaluate_answer_stream(
                question, answer_text, context, ai_client
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

    score_history = [
        ScorePoint(attempt_id=a.id, created_at=a.created_at, score=a.score) for a in attempts
    ]
    average_score = sum(a.score for a in attempts) / len(attempts)

    topic_scores: dict[int, list[int]] = {}
    for attempt in attempts:
        for section_id in session_by_id[attempt.session_id].section_ids:
            topic_scores.setdefault(section_id, []).append(attempt.score)

    section_ids = list(topic_scores.keys())
    section_names = {
        section.id: section.name
        for section in db.scalars(select(Section).where(Section.id.in_(section_ids)))
    }

    weakest_topics = sorted(
        (
            TopicStat(
                section_id=section_id,
                section_name=section_names[section_id],
                average_score=sum(scores) / len(scores),
                attempt_count=len(scores),
            )
            for section_id, scores in topic_scores.items()
        ),
        key=lambda topic: topic.average_score,
    )[:5]

    return StatsRead(
        total_attempts=len(attempts),
        average_score=average_score,
        score_history=score_history,
        weakest_topics=weakest_topics,
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
        section_ids=session.section_ids,
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
