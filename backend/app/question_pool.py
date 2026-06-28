import asyncio

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.ai.client import AIClientError, MissingApiKeyError
from app.ai.generate import generate_questions, generate_quiz_questions
from app.ai.provider import AIProvider
from app.config import settings
from app.models import QuestionBank, Section
from app.rate_limit import check_ai_rate_limit
from app.section_access import get_owned_sections


def scope_key(section_ids: list[int]) -> list[int]:
    return sorted(set(section_ids))


def remove_orphaned_bank_rows(db: DBSession, user_id: int) -> int:
    """Deletes this user's QuestionBank rows that reference a section that no
    longer exists - questions a deleted section left behind can never be
    matched again (starting a session always requires currently-existing
    sections), so they'd otherwise sit there as dead rows forever.

    Acts as a general-purpose safety net rather than something tied to one
    specific delete call: it re-checks *all* of the user's bank rows against
    *all* of their current sections, so it also mops up anything that became
    orphaned through some other path (e.g. rows left over from before this
    cleanup existed).
    """
    rows = list(db.scalars(select(QuestionBank).where(QuestionBank.user_id == user_id)))
    if not rows:
        return 0

    existing_section_ids = set(db.scalars(select(Section.id).where(Section.user_id == user_id)))
    orphaned = [row for row in rows if not set(row.section_ids).issubset(existing_section_ids)]
    for row in orphaned:
        db.delete(row)
    if orphaned:
        db.commit()
    return len(orphaned)


def matching_bank_rows(
    db: DBSession,
    user_id: int,
    mode: str,
    format_: str,
    difficulty: str,
    language: str,
    scope: list[int],
    section_mode: str = "or",
) -> list[QuestionBank]:
    candidates = list(db.scalars(
        select(QuestionBank).where(
            QuestionBank.user_id == user_id,
            QuestionBank.mode == mode,
            QuestionBank.format == format_,
            QuestionBank.difficulty == difficulty,
            QuestionBank.language == language,
        )
    ))
    if section_mode == "and":
        return [row for row in candidates if scope_key(row.section_ids) == scope]
    # "or": question belongs to at least one of the selected sections
    scope_set = set(scope)
    return [row for row in candidates if any(sid in scope_set for sid in row.section_ids)]


def bank_rows_from_batch(
    generated_batch: list[dict],
    user_id: int,
    mode: str,
    format_: str,
    difficulty: str,
    language: str,
    scope: list[int],
) -> list[QuestionBank]:
    return [
        QuestionBank(
            user_id=user_id,
            mode=mode,
            format=format_,
            difficulty=difficulty,
            language=language,
            section_ids=scope,
            theme=item["theme"],
            question=item["question"],
            category=item["category"],
            options=item.get("options"),
            correct_index=item.get("correct_index"),
            hint=item["hint"],
            explanation=item["explanation"],
        )
        for item in generated_batch
    ]


async def generate_batch(
    sections: list[Section],
    mode: str,
    format_: str,
    count: int,
    ai_client: AIProvider,
    difficulty: str,
    avoid_themes: list[str],
    language: str,
) -> list[dict]:
    if format_ == "quiz":
        return await generate_quiz_questions(
            sections, mode, count, ai_client, difficulty=difficulty, avoid_themes=avoid_themes, language=language
        )
    return await generate_questions(
        sections, mode, count, ai_client, difficulty=difficulty, avoid_themes=avoid_themes, language=language
    )


# Tracks (user, mode, format, difficulty, language, scope) combinations currently
# being topped up in the background, so a slow top-up can't be triggered twice
# (e.g. once from session-start, once from the next low-watermark check) and
# burn extra AI tokens generating questions nobody asked for yet.
_replenishing: set[tuple] = set()


def pool_key(
    user_id: int, mode: str, format_: str, difficulty: str, language: str, scope: list[int]
) -> tuple:
    return (user_id, mode, format_, difficulty, language, tuple(scope))


async def replenish_pool(
    key: tuple,
    user_id: int,
    mode: str,
    format_: str,
    difficulty: str,
    language: str,
    scope: list[int],
    section_ids: list[int],
    section_mode: str,
    avoid_themes: list[str],
    ai_client: AIProvider,
    session_factory,
) -> None:
    """Best-effort background top-up of a few questions for a pool that's about
    to (or already did) run dry. Deliberately small (`background_question_batch_size`,
    not the full reactive batch) and rate-limit-aware, since this is speculative
    generation that may never get used if the user changes settings or stops -
    keeping it small bounds how many tokens that speculation can waste.
    """
    try:
        check_ai_rate_limit(user_id)
    except HTTPException:
        return

    db = session_factory()
    try:
        sections = get_owned_sections(db, section_ids, user_id)
        # For "or" multi-section sessions generate per section so every bank row
        # carries a single-section scope and can be attributed in stats.
        if section_mode == "or" and len(sections) > 1:
            section_map = {s.id: s for s in sections}
            per_section_count = max(1, settings.background_question_batch_size // len(sections))
            new_rows = []
            for i, sid in enumerate(section_ids):
                if i > 0:
                    await asyncio.sleep(1)
                sec_scope = scope_key([sid])
                batch = await generate_batch(
                    [section_map[sid]], mode, format_, per_section_count, ai_client,
                    difficulty=difficulty, avoid_themes=avoid_themes, language=language,
                )
                new_rows += bank_rows_from_batch(batch, user_id, mode, format_, difficulty, language, sec_scope)
        else:
            generated_batch = await generate_batch(
                sections, mode, format_, settings.background_question_batch_size, ai_client,
                difficulty=difficulty, avoid_themes=avoid_themes, language=language,
            )
            new_rows = bank_rows_from_batch(generated_batch, user_id, mode, format_, difficulty, language, scope)
        db.add_all(new_rows)
        db.commit()
    except (AIClientError, MissingApiKeyError, HTTPException):
        pass  # Best effort - the next live request just falls back to generating synchronously.
    finally:
        db.close()
        _replenishing.discard(key)


def schedule_replenish_if_low(
    background_tasks: BackgroundTasks,
    matching: list[QuestionBank],
    unused_after: int,
    user_id: int,
    mode: str,
    format_: str,
    difficulty: str,
    language: str,
    scope: list[int],
    section_ids: list[int],
    section_mode: str,
    ai_client: AIProvider,
    session_factory,
) -> None:
    if unused_after > 0 or settings.background_question_batch_size <= 0:
        return
    key = pool_key(user_id, mode, format_, difficulty, language, scope)
    if key in _replenishing:
        return
    _replenishing.add(key)
    avoid_themes = [row.theme for row in matching]
    background_tasks.add_task(
        replenish_pool,
        key,
        user_id,
        mode,
        format_,
        difficulty,
        language,
        scope,
        section_ids,
        section_mode,
        avoid_themes,
        ai_client,
        session_factory,
    )
