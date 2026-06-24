from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.ai.client import AIClientError, MissingApiKeyError, get_ai_client
from app.ai.provider import AIProvider
from app.auth.deps import get_current_user
from app.db import get_db
from app.models import QuestionBank, User
from app.question_pool import bank_rows_from_batch, generate_batch, matching_bank_rows, scope_key
from app.rate_limit import enforce_ai_rate_limit
from app.schemas import QuestionBankGenerateRequest, QuestionBankItemRead
from app.section_access import get_owned_sections

router = APIRouter(prefix="/question-bank", tags=["question-bank"])


def _get_owned_item(db: DBSession, item_id: int, user_id: int) -> QuestionBank:
    item = db.get(QuestionBank, item_id)
    if item is None or item.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return item


@router.get("", response_model=list[QuestionBankItemRead])
def list_question_bank(
    section_id: int | None = None,
    mode: str | None = None,
    format: str | None = None,
    difficulty: str | None = None,
    language: str | None = None,
    unused_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[QuestionBank]:
    query = select(QuestionBank).where(QuestionBank.user_id == current_user.id)
    if mode:
        query = query.where(QuestionBank.mode == mode)
    if format:
        query = query.where(QuestionBank.format == format)
    if difficulty:
        query = query.where(QuestionBank.difficulty == difficulty)
    if language:
        query = query.where(QuestionBank.language == language)
    if unused_only:
        query = query.where(QuestionBank.used_at.is_(None))

    rows = list(db.scalars(query.order_by(QuestionBank.created_at.desc())))
    if section_id is not None:
        rows = [row for row in rows if section_id in row.section_ids]

    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    return rows[offset : offset + limit]


@router.post("/generate", response_model=list[QuestionBankItemRead], status_code=status.HTTP_201_CREATED)
async def generate_question_bank_items(
    payload: QuestionBankGenerateRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(enforce_ai_rate_limit),
    ai_client: AIProvider = Depends(get_ai_client),
) -> list[QuestionBank]:
    sections = get_owned_sections(db, payload.section_ids, current_user.id)
    scope = scope_key(payload.section_ids)
    matching = matching_bank_rows(
        db, current_user.id, payload.mode, payload.format, payload.difficulty, current_user.language, scope
    )
    avoid_themes = [row.theme for row in matching]

    try:
        generated_batch = await generate_batch(
            sections,
            payload.mode,
            payload.format,
            payload.count,
            ai_client,
            difficulty=payload.difficulty,
            avoid_themes=avoid_themes,
            language=current_user.language,
        )
    except MissingApiKeyError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except AIClientError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    new_rows = bank_rows_from_batch(
        generated_batch, current_user.id, payload.mode, payload.format, payload.difficulty,
        current_user.language, scope,
    )
    db.add_all(new_rows)
    db.commit()
    for row in new_rows:
        db.refresh(row)
    return new_rows


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question_bank_item(
    item_id: int,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    item = _get_owned_item(db, item_id, current_user.id)
    db.delete(item)
    db.commit()
