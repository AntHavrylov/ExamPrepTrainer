import asyncio
import json

from sqlalchemy import select

from app.ai.client import get_ai_client
from app.ai.generate import generate_questions, generate_quiz_questions
from app.config import settings
from app.main import app
from app.models import Document, QuestionBank, Section


class _StubAIClient:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls = 0

    async def complete(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        self.calls += 1
        return self.response_text


class _RecordingAIClient:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.messages: list[dict[str, str]] | None = None

    async def complete(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        self.messages = messages
        return self.response_text


def _override_ai_client(stub) -> None:
    app.dependency_overrides[get_ai_client] = lambda: stub


def _clear_ai_override() -> None:
    app.dependency_overrides.pop(get_ai_client, None)


def _create_section_with_document(client, headers) -> int:
    section = client.post("/sections", json={"name": "Python"}, headers=headers).json()
    client.post(
        f"/sections/{section['id']}/documents",
        json={"title": "Notes", "content": "Some interview prep notes about Python."},
        headers=headers,
    )
    return section["id"]


def _start_session(
    client,
    headers,
    section_ids: list[int],
    mode: str = "technical",
    fmt: str = "open_ended",
    difficulty: str = "medium",
) -> int:
    response = client.post(
        "/sessions",
        json={"section_ids": section_ids, "mode": mode, "format": fmt, "difficulty": difficulty},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def _open_ended_item(question: str, theme: str, category: str = "technical") -> dict:
    return {
        "question": question,
        "category": category,
        "theme": theme,
        "hint": "A small nudge.",
        "explanation": "A model explanation.",
    }


def _quiz_item(question: str, theme: str, options: list[str], correct_index: int, category: str = "technical") -> dict:
    return {
        "question": question,
        "category": category,
        "options": options,
        "correct_index": correct_index,
        "theme": theme,
        "hint": "A small nudge.",
        "explanation": "A model explanation.",
    }


def test_second_next_call_reuses_bank_without_ai_call(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "question_bank_batch_size", 2)
    monkeypatch.setattr(settings, "background_question_batch_size", 0)
    headers = make_user("bank-reuse@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, [section_id])

    batch_json = json.dumps(
        [
            _open_ended_item("What is the GIL?", "python gil"),
            _open_ended_item("Explain decorators.", "decorators"),
        ]
    )
    stub = _StubAIClient(batch_json)
    _override_ai_client(stub)
    try:
        first = client.post(f"/sessions/{session_id}/next", headers=headers)
        second = client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    assert first.status_code == 200
    assert second.status_code == 200
    assert stub.calls == 1
    assert first.json()["question"] != second.json()["question"]


def test_pool_exhaustion_triggers_one_more_batched_generation(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "question_bank_batch_size", 1)
    monkeypatch.setattr(settings, "background_question_batch_size", 0)
    headers = make_user("bank-exhaust@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, [section_id])

    single_json = json.dumps([_open_ended_item("What is the GIL?", "python gil")])
    stub = _StubAIClient(single_json)
    _override_ai_client(stub)
    try:
        for _ in range(3):
            response = client.post(f"/sessions/{session_id}/next", headers=headers)
            assert response.status_code == 200
    finally:
        _clear_ai_override()

    assert stub.calls == 3


def test_cross_session_reuse_same_scope(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "question_bank_batch_size", 2)
    monkeypatch.setattr(settings, "background_question_batch_size", 0)
    headers = make_user("bank-cross-session@example.com")
    section_id = _create_section_with_document(client, headers)

    batch_json = json.dumps(
        [
            _open_ended_item("What is the GIL?", "python gil"),
            _open_ended_item("Explain decorators.", "decorators"),
        ]
    )
    stub = _StubAIClient(batch_json)
    _override_ai_client(stub)
    try:
        session_a = _start_session(client, headers, [section_id])
        first = client.post(f"/sessions/{session_a}/next", headers=headers)
        assert first.status_code == 200
        assert stub.calls == 1

        session_b = _start_session(client, headers, [section_id])
        second = client.post(f"/sessions/{session_b}/next", headers=headers)
        assert second.status_code == 200
    finally:
        _clear_ai_override()

    assert stub.calls == 1
    assert first.json()["question"] != second.json()["question"]


def test_different_mode_does_not_share_pool(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "question_bank_batch_size", 1)
    monkeypatch.setattr(settings, "background_question_batch_size", 0)
    headers = make_user("bank-mode-split@example.com")
    section_id = _create_section_with_document(client, headers)

    technical_json = json.dumps([_open_ended_item("What is the GIL?", "python gil")])
    behavioral_json = json.dumps(
        [_open_ended_item("Tell me about a conflict.", "conflict", category="behavioral")]
    )
    stub = _StubAIClient(technical_json)
    _override_ai_client(stub)
    try:
        session_technical = _start_session(client, headers, [section_id], mode="technical")
        client.post(f"/sessions/{session_technical}/next", headers=headers)

        stub.response_text = behavioral_json
        session_behavioral = _start_session(client, headers, [section_id], mode="behavioral")
        client.post(f"/sessions/{session_behavioral}/next", headers=headers)
    finally:
        _clear_ai_override()

    assert stub.calls == 2


def test_duplicate_section_ids_share_pool_and_are_stored_deduped(client, make_user, db_session, monkeypatch):
    monkeypatch.setattr(settings, "question_bank_batch_size", 2)
    monkeypatch.setattr(settings, "background_question_batch_size", 0)
    headers = make_user("bank-dedup@example.com")
    section_id = _create_section_with_document(client, headers)

    batch_json = json.dumps(
        [
            _open_ended_item("What is the GIL?", "python gil"),
            _open_ended_item("Explain decorators.", "decorators"),
        ]
    )
    stub = _StubAIClient(batch_json)
    _override_ai_client(stub)
    try:
        session_a = _start_session(client, headers, [section_id])
        client.post(f"/sessions/{session_a}/next", headers=headers)
        assert stub.calls == 1

        session_b = _start_session(client, headers, [section_id, section_id])
        response = client.post(f"/sessions/{session_b}/next", headers=headers)
        assert response.status_code == 200
    finally:
        _clear_ai_override()

    assert stub.calls == 1

    rows = list(db_session.scalars(select(QuestionBank)))
    assert len(rows) == 2
    assert all(row.section_ids == [section_id] for row in rows)


def _section_with_document() -> Section:
    section = Section(id=1, user_id=1, name="Python")
    section.documents = [Document(id=1, section_id=1, title="Notes", content="Some Python notes.")]
    return section


def test_avoid_themes_included_in_open_ended_prompt():
    valid_json = json.dumps([_open_ended_item("Q1", "general")])
    stub = _RecordingAIClient(valid_json)
    asyncio.run(
        generate_questions(
            [_section_with_document()], "technical", 1, stub, avoid_themes=["python gil", "decorators"]
        )
    )

    user_message = stub.messages[1]["content"]
    assert "Avoid repeating these previously covered topics: python gil, decorators." in user_message


def test_avoid_themes_included_in_quiz_prompt():
    valid_json = json.dumps([_quiz_item("Q1", "general", ["a", "b", "c", "d"], 0)])
    stub = _RecordingAIClient(valid_json)
    asyncio.run(
        generate_quiz_questions(
            [_section_with_document()], "technical", 1, stub, avoid_themes=["python gil"]
        )
    )

    user_message = stub.messages[1]["content"]
    assert "Avoid repeating these previously covered topics: python gil." in user_message


def test_difficulty_instruction_included_in_prompt():
    valid_json = json.dumps([_open_ended_item("Q1", "general")])
    stub = _RecordingAIClient(valid_json)
    asyncio.run(generate_questions([_section_with_document()], "technical", 1, stub, difficulty="hard"))

    user_message = stub.messages[1]["content"]
    assert "Make questions challenging" in user_message


def test_different_difficulty_does_not_share_pool(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "question_bank_batch_size", 1)
    monkeypatch.setattr(settings, "background_question_batch_size", 0)
    headers = make_user("bank-difficulty-split@example.com")
    section_id = _create_section_with_document(client, headers)

    easy_json = json.dumps([_open_ended_item("What is the GIL?", "python gil")])
    hard_json = json.dumps([_open_ended_item("Explain the GIL's edge cases.", "python gil edge cases")])
    stub = _StubAIClient(easy_json)
    _override_ai_client(stub)
    try:
        session_easy = _start_session(client, headers, [section_id], difficulty="easy")
        client.post(f"/sessions/{session_easy}/next", headers=headers)

        stub.response_text = hard_json
        session_hard = _start_session(client, headers, [section_id], difficulty="hard")
        client.post(f"/sessions/{session_hard}/next", headers=headers)
    finally:
        _clear_ai_override()

    assert stub.calls == 2


def test_different_language_does_not_share_pool(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "question_bank_batch_size", 1)
    monkeypatch.setattr(settings, "background_question_batch_size", 0)
    headers = make_user("bank-language-split@example.com")
    section_id = _create_section_with_document(client, headers)

    en_json = json.dumps([_open_ended_item("What is the GIL?", "python gil")])
    uk_json = json.dumps([_open_ended_item("Що таке GIL?", "python gil")])
    stub = _StubAIClient(en_json)
    _override_ai_client(stub)
    try:
        session_en = _start_session(client, headers, [section_id])
        client.post(f"/sessions/{session_en}/next", headers=headers)

        language_response = client.put("/settings/language", json={"language": "uk"}, headers=headers)
        assert language_response.status_code == 200

        stub.response_text = uk_json
        session_uk = _start_session(client, headers, [section_id])
        client.post(f"/sessions/{session_uk}/next", headers=headers)
    finally:
        _clear_ai_override()

    assert stub.calls == 2


def test_next_question_exposes_hint_but_not_explanation(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "question_bank_batch_size", 1)
    headers = make_user("bank-hint-no-leak@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, [section_id])

    item = _open_ended_item("What is the GIL?", "python gil")
    stub = _StubAIClient(json.dumps([item]))
    _override_ai_client(stub)
    try:
        response = client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    assert response.status_code == 200
    body = response.json()
    assert body["hint"] == item["hint"]
    assert "explanation" not in body


def test_answer_exposes_explanation_for_open_ended(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "question_bank_batch_size", 1)
    headers = make_user("bank-explanation-open@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, [section_id])

    item = _open_ended_item("What is the GIL?", "python gil")
    _override_ai_client(_StubAIClient(json.dumps([item])))
    try:
        client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    eval_json = json.dumps({"score": 4, "feedback": "Partial.", "strengths": [], "gaps": ["depth"]})
    _override_ai_client(_StubAIClient(eval_json))
    try:
        response = client.post(
            f"/sessions/{session_id}/answer", json={"answer": "Some answer"}, headers=headers
        )
    finally:
        _clear_ai_override()

    assert response.status_code == 200
    assert response.json()["explanation"] == item["explanation"]


def test_answer_exposes_explanation_for_quiz(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "question_bank_batch_size", 1)
    headers = make_user("bank-explanation-quiz@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, [section_id], fmt="quiz")

    item = _quiz_item("Which keyword defines a coroutine?", "coroutines", ["def", "async def", "x", "y"], 1)
    _override_ai_client(_StubAIClient(json.dumps([item])))
    try:
        client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    response = client.post(f"/sessions/{session_id}/answer", json={"selected_index": 0}, headers=headers)

    assert response.status_code == 200
    assert response.json()["explanation"] == item["explanation"]


def test_start_session_prewarms_pool_in_background_when_empty(client, make_user, db_session, monkeypatch):
    monkeypatch.setattr(settings, "background_question_batch_size", 2)
    headers = make_user("bank-prewarm@example.com")
    section_id = _create_section_with_document(client, headers)

    batch_json = json.dumps(
        [
            _open_ended_item("What is the GIL?", "python gil"),
            _open_ended_item("Explain decorators.", "decorators"),
        ]
    )
    stub = _StubAIClient(batch_json)
    _override_ai_client(stub)
    try:
        _start_session(client, headers, [section_id])
    finally:
        _clear_ai_override()

    # Pre-warmed before any /next call was ever made.
    assert stub.calls == 1
    rows = list(db_session.scalars(select(QuestionBank)))
    assert len(rows) == 2
    assert all(row.used_at is None for row in rows)


def test_next_question_replenishes_pool_in_background_once_it_runs_dry(
    client, make_user, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "question_bank_batch_size", 1)
    monkeypatch.setattr(settings, "background_question_batch_size", 2)
    headers = make_user("bank-replenish@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, [section_id])

    single_json = json.dumps([_open_ended_item("What is the GIL?", "python gil")])
    stub = _StubAIClient(single_json)
    _override_ai_client(stub)
    try:
        response = client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    assert response.status_code == 200
    # One reactive call for the question actually served, one background call
    # to top the pool back up - not more. (The stub always returns the same
    # one-item canned response regardless of the requested count, so the
    # background call adds exactly one more row here, not a full batch.)
    assert stub.calls == 2

    rows = list(db_session.scalars(select(QuestionBank)))
    assert len(rows) == 2
    unused = [row for row in rows if row.used_at is None]
    assert len(unused) == 1


def test_background_replenish_does_nothing_when_disabled(client, make_user, db_session, monkeypatch):
    monkeypatch.setattr(settings, "question_bank_batch_size", 1)
    monkeypatch.setattr(settings, "background_question_batch_size", 0)
    headers = make_user("bank-replenish-disabled@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, [section_id])

    single_json = json.dumps([_open_ended_item("What is the GIL?", "python gil")])
    stub = _StubAIClient(single_json)
    _override_ai_client(stub)
    try:
        client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    assert stub.calls == 1
    rows = list(db_session.scalars(select(QuestionBank)))
    assert len(rows) == 1


def test_background_replenish_skips_silently_when_rate_limited(
    client, make_user, db_session, monkeypatch
):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "question_bank_batch_size", 1)
    # Pre-warming at session start would itself consume the rate-limit budget
    # we're about to set to 1, before this test's actual /next call even
    # happens - disable it for session creation, then turn it back on only
    # for the low-watermark check this test is actually exercising.
    monkeypatch.setattr(app_settings, "background_question_batch_size", 0)
    headers = make_user("bank-replenish-ratelimited@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, [section_id])

    monkeypatch.setattr(app_settings, "background_question_batch_size", 2)
    monkeypatch.setattr(app_settings, "ai_rate_limit_max_requests", 1)

    single_json = json.dumps([_open_ended_item("What is the GIL?", "python gil")])
    stub = _StubAIClient(single_json)
    _override_ai_client(stub)
    try:
        response = client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    # The foreground request itself stayed within the limit and succeeded...
    assert response.status_code == 200
    assert stub.calls == 1
    # ...but the background top-up saw the bucket already at the limit and
    # quietly skipped rather than erroring or spending another call.
    rows = list(db_session.scalars(select(QuestionBank)))
    assert len(rows) == 1
