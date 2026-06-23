from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.client import AIClientError, OpenRouterClient, get_ai_client
from app.ai.context import build_context
from app.ai.evaluate import evaluate_answer
from app.ai.generate import generate_questions
from app.config import settings
from app.db import get_db
from app.models import User
from app.rate_limit import enforce_ai_rate_limit
from app.schemas import (
    EvaluateAnswerRequest,
    EvaluationRead,
    GenerateQuestionsRequest,
    QuestionRead,
)
from app.section_access import get_owned_sections

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/ping")
async def ping(
    current_user: User = Depends(enforce_ai_rate_limit),
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
    current_user: User = Depends(enforce_ai_rate_limit),
    ai_client: OpenRouterClient = Depends(get_ai_client),
) -> list[dict[str, str]]:
    sections = get_owned_sections(db, payload.section_ids, current_user.id)

    try:
        return await generate_questions(sections, payload.mode, payload.count, ai_client)
    except AIClientError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.post("/evaluate", response_model=EvaluationRead)
async def evaluate(
    payload: EvaluateAnswerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(enforce_ai_rate_limit),
    ai_client: OpenRouterClient = Depends(get_ai_client),
) -> dict:
    sections = get_owned_sections(db, payload.section_ids, current_user.id)
    context = build_context(
        sections, settings.max_generation_context_chars, query=f"{payload.question} {payload.answer}"
    )

    try:
        return await evaluate_answer(payload.question, payload.answer, context, ai_client)
    except AIClientError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
