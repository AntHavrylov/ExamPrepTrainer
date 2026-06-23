from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.ai.client import AIClientError, OpenRouterClient, get_ai_client
from app.ai.context import build_context
from app.ai.evaluate import evaluate_answer
from app.ai.generate import generate_questions, generate_quiz_questions
from app.auth.deps import get_current_user
from app.config import settings
from app.db import get_db
from app.models import Attempt, User
from app.models import Session as TrainingSession
from app.schemas import (
    AnswerRequest,
    AnswerResultRead,
    AttemptSummaryRead,
    NextQuestionRead,
    SessionRead,
    SessionSummaryRead,
    StartSessionRequest,
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
    current_user: User = Depends(get_current_user),
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

    sections = get_owned_sections(db, session.section_ids, current_user.id)
    context = build_context(sections, settings.max_generation_context_chars)

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
