import json

from app.ai.client import get_ai_client
from app.ai.context import build_context
from app.config import settings
from app.main import app
from app.models import Document, Section


class _StubAIClient:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls = 0

    async def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls += 1
        return self.response_text


class _FlakyJSONAIClient:
    def __init__(self, bad_response: str, good_response: str):
        self.bad_response = bad_response
        self.good_response = good_response
        self.calls = 0

    async def complete(self, messages: list[dict[str, str]]) -> str:
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


def test_generate_parses_valid_json(client, make_user):
    headers = make_user("gen-a@example.com")
    section_id = _create_section_with_document(client, headers)

    valid_json = json.dumps(
        [
            {"question": "What is the GIL?", "category": "technical"},
            {"question": "Tell me about a time you debugged a hard issue.", "category": "behavioral"},
        ]
    )
    _override_ai_client(_StubAIClient(valid_json))
    try:
        response = client.post(
            "/ai/generate",
            json={"section_ids": [section_id], "mode": "mixed", "count": 2},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0] == {"question": "What is the GIL?", "category": "technical"}


def test_generate_parses_json_wrapped_in_prose_and_fences(client, make_user):
    headers = make_user("gen-b@example.com")
    section_id = _create_section_with_document(client, headers)

    messy = (
        "Sure! Here are your questions:\n"
        "```json\n"
        '[{"question": "Explain decorators.", "category": "technical"}]\n'
        "```\n"
        "Let me know if you need more."
    )
    _override_ai_client(_StubAIClient(messy))
    try:
        response = client.post(
            "/ai/generate",
            json={"section_ids": [section_id], "mode": "technical", "count": 1},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    assert response.status_code == 200
    assert response.json() == [{"question": "Explain decorators.", "category": "technical"}]


def test_generate_retries_once_on_invalid_json(client, make_user):
    headers = make_user("gen-e@example.com")
    section_id = _create_section_with_document(client, headers)

    good_json = json.dumps([{"question": "Q1", "category": "technical"}])
    stub = _FlakyJSONAIClient("not json at all", good_json)
    _override_ai_client(stub)
    try:
        response = client.post(
            "/ai/generate",
            json={"section_ids": [section_id], "mode": "mixed", "count": 1},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    assert response.status_code == 200
    assert stub.calls == 2
    assert response.json() == [{"question": "Q1", "category": "technical"}]


def test_generate_fails_gracefully_when_json_never_parses(client, make_user):
    headers = make_user("gen-f@example.com")
    section_id = _create_section_with_document(client, headers)

    stub = _FlakyJSONAIClient("still not json", "also not json")
    _override_ai_client(stub)
    try:
        response = client.post(
            "/ai/generate",
            json={"section_ids": [section_id], "mode": "mixed", "count": 1},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    assert response.status_code == 503


def test_generate_rejects_another_users_section(client, make_user):
    headers_a = make_user("gen-c1@example.com")
    headers_b = make_user("gen-c2@example.com")
    section_id = _create_section_with_document(client, headers_a)

    response = client.post(
        "/ai/generate",
        json={"section_ids": [section_id], "mode": "mixed", "count": 1},
        headers=headers_b,
    )
    assert response.status_code in (403, 404)


def test_generate_count_over_cap_returns_422(client, make_user):
    headers = make_user("gen-d@example.com")
    section_id = _create_section_with_document(client, headers)

    response = client.post(
        "/ai/generate",
        json={
            "section_ids": [section_id],
            "mode": "mixed",
            "count": settings.max_questions_per_generate + 1,
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_build_context_respects_char_budget():
    section = Section(id=1, user_id=1, name="Long Section")
    section.documents = [Document(id=1, section_id=1, title="Doc", content="x" * 1000)]

    context = build_context([section], char_budget=50)

    assert len(context) <= 50
