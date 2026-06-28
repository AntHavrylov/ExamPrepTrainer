import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.ai.client import AIClientError, MissingApiKeyError, get_ai_client
from app.ai.provider import AIProvider
from app.auth.deps import get_current_user
from app.db import get_db, get_session_factory
from app.models import QuestionBank, User
from app import generation_jobs
from app.question_pool import bank_rows_from_batch, generate_batch, matching_bank_rows, scope_key
from app.rate_limit import enforce_ai_rate_limit
from app.schemas import (
    GenerationJobResponse,
    GenerationJobStatus,
    QuestionBankGenerateRequest,
    QuestionBankItemRead,
)
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
    limit: int = 500,
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

    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    return rows[offset : offset + limit]


# Route must be declared before /{item_id} routes to avoid "jobs" being
# matched as an item_id path parameter.

@router.get("/jobs/{job_id}", response_model=GenerationJobStatus)
def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> GenerationJobStatus:
    job = generation_jobs.get_job(job_id)
    if job is None or job.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return GenerationJobStatus(
        job_id=job.job_id,
        status=job.status,
        count=job.count,
        error=job.error,
    )


async def _run_generation(
    job_id: str,
    payload: QuestionBankGenerateRequest,
    user_id: int,
    language: str,
    session_factory,
    ai_client: AIProvider,
) -> None:
    generation_jobs.mark_running(job_id)

    # Phase 1: read all needed data, then release the DB connection.
    # AI calls below can take 10-60 s; holding a connection that long starves the
    # pool and blocks other requests on the single-threaded event loop.
    db = session_factory()
    try:
        try:
            sections = get_owned_sections(db, payload.section_ids, user_id)
        except HTTPException as exc:
            generation_jobs.fail_job(job_id, exc.detail if isinstance(exc.detail, str) else str(exc.detail))
            return

        # Eagerly load the lazy `documents` relationship so Section objects
        # remain fully usable after the session is closed.
        for s in sections:
            list(s.documents)

        if len(payload.section_ids) > 1:
            section_map = {s.id: s for s in sections}
            k = len(payload.section_ids)
            base, remainder = payload.count // k, payload.count % k
            per_section_plan: list[tuple] = []
            for i, sid in enumerate(payload.section_ids):
                sec_count = base + (1 if i < remainder else 0)
                if sec_count == 0:
                    continue
                sec_scope = scope_key([sid])
                sec_matching = matching_bank_rows(
                    db, user_id, payload.mode, payload.format,
                    payload.difficulty, language, sec_scope,
                )
                avoid = [row.theme for row in sec_matching]
                per_section_plan.append((i, [section_map[sid]], sec_count, sec_scope, avoid))
        else:
            scope = scope_key(payload.section_ids)
            matching = matching_bank_rows(
                db, user_id, payload.mode, payload.format, payload.difficulty, language, scope,
            )
            avoid_themes = [row.theme for row in matching]

        db.expunge_all()  # detach ORM objects so they survive session close
    finally:
        db.close()  # release connection before the long AI calls

    # Phase 2: AI generation — no DB connection held during these calls.
    try:
        new_rows = []
        if len(payload.section_ids) > 1:
            for i, secs, sec_count, sec_scope, avoid in per_section_plan:
                if i > 0:
                    await asyncio.sleep(1)
                batch = await generate_batch(
                    secs, payload.mode, payload.format, sec_count,
                    ai_client, difficulty=payload.difficulty,
                    avoid_themes=avoid, language=language,
                )
                new_rows += bank_rows_from_batch(
                    batch, user_id, payload.mode, payload.format,
                    payload.difficulty, language, sec_scope,
                )
        else:
            batch = await generate_batch(
                sections, payload.mode, payload.format, payload.count,
                ai_client, difficulty=payload.difficulty,
                avoid_themes=avoid_themes, language=language,
            )
            new_rows = bank_rows_from_batch(
                batch, user_id, payload.mode, payload.format,
                payload.difficulty, language, scope,
            )
    except HTTPException as exc:
        generation_jobs.fail_job(job_id, exc.detail if isinstance(exc.detail, str) else str(exc.detail))
        return
    except MissingApiKeyError as exc:
        generation_jobs.fail_job(job_id, str(exc))
        return
    except AIClientError as exc:
        generation_jobs.fail_job(job_id, str(exc))
        return
    except Exception as exc:
        generation_jobs.fail_job(job_id, f"Unexpected error: {exc}")
        return

    # Phase 3: persist — fresh connection just for the write.
    db = session_factory()
    try:
        db.add_all(new_rows)
        db.commit()
        generation_jobs.complete_job(job_id, len(new_rows))
    except Exception as exc:
        generation_jobs.fail_job(job_id, f"Unexpected error saving questions: {exc}")
    finally:
        db.close()


@router.post("/generate", response_model=GenerationJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_question_bank_items(
    payload: QuestionBankGenerateRequest,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(enforce_ai_rate_limit),
    ai_client: AIProvider = Depends(get_ai_client),
    session_factory=Depends(get_session_factory),
) -> GenerationJobResponse:
    # Validate synchronously so the client gets an immediate error code.
    get_owned_sections(db, payload.section_ids, current_user.id)  # raises 404
    if not ai_client.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Add your OpenRouter API key in Settings before using AI features.",
        )
    if generation_jobs.count_active(current_user.id) >= generation_jobs.MAX_QUEUE_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Generation queue is full (max {generation_jobs.MAX_QUEUE_PER_USER} active jobs). "
                   "Wait for a job to finish before submitting another.",
        )

    job_id = str(uuid.uuid4())
    generation_jobs.create_job(job_id, current_user.id)

    background_tasks.add_task(
        _run_generation,
        job_id=job_id,
        payload=payload,
        user_id=current_user.id,
        language=current_user.language,
        session_factory=session_factory,
        ai_client=ai_client,
    )

    return GenerationJobResponse(job_id=job_id)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question_bank_item(
    item_id: int,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    item = _get_owned_item(db, item_id, current_user.id)
    db.delete(item)
    db.commit()
