from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.client import AIClientError, OpenRouterClient, get_ai_client
from app.ai.context import build_context
from app.ai.evaluate import evaluate_answer
from app.ai.generate import generate_questions
from app.auth.deps import get_current_user
from app.config import settings
from app.db import get_db
from app.models import Section, User
from app.schemas import (
    EvaluateAnswerRequest,
    EvaluationRead,
    GenerateQuestionsRequest,
    QuestionRead,
)

router = APIRouter(prefix="/ai", tags=["ai"])


def _get_owned_sections(db: Session, section_ids: list[int], user_id: int) -> list[Section]:
    sections: list[Section] = []
    for section_id in section_ids:
        section = db.get(Section, section_id)
        if section is None or section.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
        sections.append(section)
    return sections


@router.get("/ping")
async def ping(
    current_user: User = Depends(get_current_user),
    ai_client: OpenRouterClient = Depends(get_ai_client),
) -> dict[str, str]:
    try:
        text = await ai_client.complete([{"role": "user", "content": "Say hello in one word"}])
    except AIClientError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return {"response": text}


@router.post("/generate", response_model=list[QuestionRead])
async def generate(
    payload: GenerateQuestionsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ai_client: OpenRouterClient = Depends(get_ai_client),
) -> list[dict[str, str]]:
    sections = _get_owned_sections(db, payload.section_ids, current_user.id)

    try:
        return await generate_questions(sections, payload.mode, payload.count, ai_client)
    except AIClientError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.post("/evaluate", response_model=EvaluationRead)
async def evaluate(
    payload: EvaluateAnswerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ai_client: OpenRouterClient = Depends(get_ai_client),
) -> dict:
    sections = _get_owned_sections(db, payload.section_ids, current_user.id)
    context = build_context(sections, settings.max_generation_context_chars)

    try:
        return await evaluate_answer(payload.question, payload.answer, context, ai_client)
    except AIClientError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
