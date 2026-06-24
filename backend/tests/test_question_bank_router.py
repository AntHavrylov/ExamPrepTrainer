import json

from sqlalchemy import select

from app.ai.client import get_ai_client
from app.config import settings
from app.main import app
from app.models import QuestionBank


class _StubAIClient:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls = 0

    async def complete(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        self.calls += 1
        return self.response_text


class _FlakyJSONAIClient:
    def __init__(self, bad_response: str, good_response: str):
        self.bad_response = bad_response
        self.good_response = good_response
        self.calls = 0

    async def complete(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        self.calls += 1
        return self.bad_response if self.calls == 1 else self.good_response


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


def _open_ended_item(question: str, theme: str, category: str = "technical") -> dict:
    return {
        "question": question,
        "category": category,
        "theme": theme,
        "hint": "A small nudge.",
        "explanation": "A model explanation.",
    }


def _quiz_item(question: str, theme: str, options: list[str], correct_index: int) -> dict:
    return {
        "question": question,
        "category": "technical",
        "options": options,
        "correct_index": correct_index,
        "theme": theme,
        "hint": "A small nudge.",
        "explanation": "A model explanation.",
    }


def test_list_requires_auth(client):
    response = client.get("/question-bank")
    assert response.status_code == 401


def test_list_returns_empty_when_nothing_generated_yet(client, make_user):
    headers = make_user("qb-empty@example.com")
    response = client.get("/question-bank", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_generate_creates_rows_and_returns_them(client, make_user):
    headers = make_user("qb-generate@example.com")
    section_id = _create_section_with_document(client, headers)

    batch_json = json.dumps(
        [
            _open_ended_item("What is the GIL?", "python gil"),
            _open_ended_item("Explain decorators.", "decorators"),
        ]
    )
    _override_ai_client(_StubAIClient(batch_json))
    try:
        response = client.post(
            "/question-bank/generate",
            json={"section_ids": [section_id], "mode": "technical", "format": "open_ended", "count": 2},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    assert response.status_code == 201
    body = response.json()
    assert len(body) == 2
    assert body[0]["question"] == "What is the GIL?"
    assert body[0]["used_at"] is None

    listed = client.get("/question-bank", headers=headers).json()
    assert len(listed) == 2


def test_generate_rejects_another_users_section(client, make_user):
    headers_a = make_user("qb-cross-a@example.com")
    headers_b = make_user("qb-cross-b@example.com")
    section_id = _create_section_with_document(client, headers_a)

    response = client.post(
        "/question-bank/generate",
        json={"section_ids": [section_id], "mode": "mixed", "format": "open_ended", "count": 1},
        headers=headers_b,
    )
    assert response.status_code in (403, 404)


def test_generate_count_over_cap_returns_422(client, make_user):
    headers = make_user("qb-cap@example.com")
    section_id = _create_section_with_document(client, headers)

    response = client.post(
        "/question-bank/generate",
        json={
            "section_ids": [section_id],
            "mode": "mixed",
            "format": "open_ended",
            "count": settings.max_questions_per_generate + 1,
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_generate_without_api_key_returns_403(client, make_user):
    headers = make_user("qb-no-key@example.com")
    section_id = _create_section_with_document(client, headers)

    response = client.post(
        "/question-bank/generate",
        json={"section_ids": [section_id], "mode": "mixed", "format": "open_ended", "count": 1},
        headers=headers,
    )
    assert response.status_code == 403


def test_generate_fails_gracefully_when_ai_never_returns_valid_json(client, make_user):
    headers = make_user("qb-bad-json@example.com")
    section_id = _create_section_with_document(client, headers)

    stub = _FlakyJSONAIClient("not json", "still not json")
    _override_ai_client(stub)
    try:
        response = client.post(
            "/question-bank/generate",
            json={"section_ids": [section_id], "mode": "mixed", "format": "open_ended", "count": 1},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    assert response.status_code == 503


def test_generate_quiz_format_stores_options_and_correct_index(client, make_user):
    headers = make_user("qb-quiz@example.com")
    section_id = _create_section_with_document(client, headers)

    item = _quiz_item("Which keyword defines a coroutine?", "coroutines", ["def", "async def", "x", "y"], 1)
    _override_ai_client(_StubAIClient(json.dumps([item])))
    try:
        response = client.post(
            "/question-bank/generate",
            json={"section_ids": [section_id], "mode": "technical", "format": "quiz", "count": 1},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    assert response.status_code == 201
    body = response.json()[0]
    assert body["options"] == item["options"]
    assert body["correct_index"] == 1


def test_list_filters_by_format_and_unused_only(client, make_user, db_session):
    headers = make_user("qb-filter@example.com")
    section_id = _create_section_with_document(client, headers)

    open_item = _open_ended_item("What is the GIL?", "python gil")
    _override_ai_client(_StubAIClient(json.dumps([open_item])))
    try:
        client.post(
            "/question-bank/generate",
            json={"section_ids": [section_id], "mode": "technical", "format": "open_ended", "count": 1},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    quiz_item = _quiz_item("Coroutine keyword?", "coroutines", ["a", "b", "c", "d"], 0)
    _override_ai_client(_StubAIClient(json.dumps([quiz_item])))
    try:
        client.post(
            "/question-bank/generate",
            json={"section_ids": [section_id], "mode": "technical", "format": "quiz", "count": 1},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    # Mark the open-ended one as used, directly, to test unused_only filtering.
    row = db_session.scalar(select(QuestionBank).where(QuestionBank.format == "open_ended"))
    row.used_at = row.created_at
    db_session.commit()

    only_quiz = client.get("/question-bank", params={"format": "quiz"}, headers=headers).json()
    assert len(only_quiz) == 1
    assert only_quiz[0]["format"] == "quiz"

    only_unused = client.get("/question-bank", params={"unused_only": True}, headers=headers).json()
    assert len(only_unused) == 1
    assert only_unused[0]["format"] == "quiz"


def test_list_filters_by_language(client, make_user):
    headers = make_user("qb-language-filter@example.com")
    section_id = _create_section_with_document(client, headers)

    en_item = _open_ended_item("What is the GIL?", "python gil")
    _override_ai_client(_StubAIClient(json.dumps([en_item])))
    try:
        client.post(
            "/question-bank/generate",
            json={"section_ids": [section_id], "mode": "technical", "format": "open_ended", "count": 1},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    client.put("/settings/language", json={"language": "uk"}, headers=headers)
    uk_item = _open_ended_item("Що таке GIL?", "python gil")
    _override_ai_client(_StubAIClient(json.dumps([uk_item])))
    try:
        client.post(
            "/question-bank/generate",
            json={"section_ids": [section_id], "mode": "technical", "format": "open_ended", "count": 1},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    only_uk = client.get("/question-bank", params={"language": "uk"}, headers=headers).json()
    assert len(only_uk) == 1
    assert only_uk[0]["question"] == "Що таке GIL?"

    only_en = client.get("/question-bank", params={"language": "en"}, headers=headers).json()
    assert len(only_en) == 1
    assert only_en[0]["question"] == "What is the GIL?"

    unfiltered = client.get("/question-bank", headers=headers).json()
    assert len(unfiltered) == 2


def test_list_filters_by_section_id(client, make_user):
    headers = make_user("qb-section-filter@example.com")
    section_a = _create_section_with_document(client, headers)
    section_b = _create_section_with_document(client, headers)

    item_a = _open_ended_item("Question about A", "topic a")
    _override_ai_client(_StubAIClient(json.dumps([item_a])))
    try:
        client.post(
            "/question-bank/generate",
            json={"section_ids": [section_a], "mode": "mixed", "format": "open_ended", "count": 1},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    item_b = _open_ended_item("Question about B", "topic b")
    _override_ai_client(_StubAIClient(json.dumps([item_b])))
    try:
        client.post(
            "/question-bank/generate",
            json={"section_ids": [section_b], "mode": "mixed", "format": "open_ended", "count": 1},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    filtered = client.get("/question-bank", params={"section_id": section_a}, headers=headers).json()
    assert len(filtered) == 1
    assert filtered[0]["question"] == "Question about A"


def test_delete_requires_auth(client):
    response = client.delete("/question-bank/1")
    assert response.status_code == 401


def test_delete_removes_the_item(client, make_user):
    headers = make_user("qb-delete@example.com")
    section_id = _create_section_with_document(client, headers)

    item = _open_ended_item("What is the GIL?", "python gil")
    _override_ai_client(_StubAIClient(json.dumps([item])))
    try:
        generated = client.post(
            "/question-bank/generate",
            json={"section_ids": [section_id], "mode": "mixed", "format": "open_ended", "count": 1},
            headers=headers,
        ).json()
    finally:
        _clear_ai_override()

    item_id = generated[0]["id"]
    delete_response = client.delete(f"/question-bank/{item_id}", headers=headers)
    assert delete_response.status_code == 204

    listed = client.get("/question-bank", headers=headers).json()
    assert listed == []


def test_delete_rejects_another_users_item(client, make_user):
    headers_a = make_user("qb-delete-a@example.com")
    headers_b = make_user("qb-delete-b@example.com")
    section_id = _create_section_with_document(client, headers_a)

    item = _open_ended_item("What is the GIL?", "python gil")
    _override_ai_client(_StubAIClient(json.dumps([item])))
    try:
        generated = client.post(
            "/question-bank/generate",
            json={"section_ids": [section_id], "mode": "mixed", "format": "open_ended", "count": 1},
            headers=headers_a,
        ).json()
    finally:
        _clear_ai_override()

    item_id = generated[0]["id"]
    response = client.delete(f"/question-bank/{item_id}", headers=headers_b)
    assert response.status_code == 404

    # Untouched for its rightful owner.
    listed = client.get("/question-bank", headers=headers_a).json()
    assert len(listed) == 1


def test_delete_nonexistent_item_returns_404(client, make_user):
    headers = make_user("qb-delete-missing@example.com")
    response = client.delete("/question-bank/999999", headers=headers)
    assert response.status_code == 404


def test_deleting_a_used_question_does_not_affect_its_past_attempt(client, make_user, monkeypatch):
    # Disable the background pool top-up for this test - it's not what's being
    # tested here, and would otherwise leave an extra unused row behind.
    monkeypatch.setattr(settings, "background_question_batch_size", 0)
    headers = make_user("qb-delete-used@example.com")
    section_id = _create_section_with_document(client, headers)

    item = _open_ended_item("What is the GIL?", "python gil")
    _override_ai_client(_StubAIClient(json.dumps([item])))
    try:
        session_id = client.post(
            "/sessions",
            json={"section_ids": [section_id], "mode": "technical", "format": "open_ended"},
            headers=headers,
        ).json()["id"]
        client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    used_items = client.get("/question-bank", headers=headers).json()
    assert len(used_items) == 1
    item_id = used_items[0]["id"]
    assert used_items[0]["used_at"] is not None

    delete_response = client.delete(f"/question-bank/{item_id}", headers=headers)
    assert delete_response.status_code == 204

    # The Attempt copied its own content at creation time, so it's unaffected.
    summary = client.get(f"/sessions/{session_id}", headers=headers).json()
    assert summary["attempts"][0]["question"] == "What is the GIL?"
