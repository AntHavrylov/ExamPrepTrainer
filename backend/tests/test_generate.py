import asyncio
import json

import pytest

from app.ai.client import AIClientError, get_ai_client
from app.ai.context import build_context
from app.ai.generate import generate_questions, generate_quiz_questions
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


class _RecordingAIClient:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.messages: list[dict[str, str]] | None = None

    async def complete(self, messages: list[dict[str, str]]) -> str:
        self.messages = messages
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
            {
                "question": "What is the GIL?",
                "category": "technical",
                "theme": "python gil",
                "hint": "Think about thread safety.",
                "explanation": "The GIL serializes bytecode execution across threads.",
            },
            {
                "question": "Tell me about a time you debugged a hard issue.",
                "category": "behavioral",
                "theme": "debugging",
                "hint": "Use the STAR method.",
                "explanation": "A strong answer covers situation, task, action, and result.",
            },
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
        '[{"question": "Explain decorators.", "category": "technical", "theme": "decorators", '
        '"hint": "Think about functions that wrap functions.", '
        '"explanation": "A decorator wraps a function to extend its behavior."}]\n'
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

    good_json = json.dumps(
        [
            {
                "question": "Q1",
                "category": "technical",
                "theme": "general",
                "hint": "A small nudge.",
                "explanation": "A model explanation.",
            }
        ]
    )
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


def test_generate_treats_empty_array_as_failure_and_retries(client, make_user):
    headers = make_user("gen-empty@example.com")
    section_id = _create_section_with_document(client, headers)

    good_json = json.dumps(
        [
            {
                "question": "Q1",
                "category": "technical",
                "theme": "general",
                "hint": "A small nudge.",
                "explanation": "A model explanation.",
            }
        ]
    )
    stub = _FlakyJSONAIClient("[]", good_json)
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


def test_generate_fails_gracefully_when_empty_array_on_both_attempts(client, make_user):
    headers = make_user("gen-empty-both@example.com")
    section_id = _create_section_with_document(client, headers)

    stub = _FlakyJSONAIClient("[]", "[]")
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


def test_build_context_without_query_keeps_document_order_when_truncating():
    section = Section(id=1, user_id=1, name="Notes")
    section.documents = [
        Document(id=1, section_id=1, title="First", content="x" * 100),
        Document(id=2, section_id=1, title="Second", content="y" * 100),
    ]

    context = build_context([section], char_budget=40)

    assert "First" in context
    assert "Second" not in context


def test_build_context_ranks_relevant_document_first_when_truncating():
    section = Section(id=1, user_id=1, name="Notes")
    section.documents = [
        Document(id=1, section_id=1, title="Irrelevant", content="banana bread recipe " * 20),
        Document(id=2, section_id=1, title="Relevant", content="python asyncio event loop " * 20),
    ]

    context = build_context([section], char_budget=80, query="explain python asyncio")

    assert "Relevant" in context
    assert "Irrelevant" not in context


def test_build_context_with_query_is_unchanged_when_everything_fits():
    section = Section(id=1, user_id=1, name="Notes")
    section.documents = [Document(id=1, section_id=1, title="Doc", content="short content")]

    context = build_context([section], char_budget=1000, query="irrelevant query terms")

    assert context == "## Section: Notes\n### Doc\nshort content\n"


def _make_section() -> Section:
    section = Section(id=1, user_id=1, name="Python")
    section.documents = [Document(id=1, section_id=1, title="Notes", content="Some Python notes.")]
    return section


def test_generate_quiz_questions_parses_valid_json():
    valid_json = json.dumps(
        [
            {
                "question": "Which keyword defines a coroutine?",
                "category": "technical",
                "options": ["def", "async def", "coroutine", "await"],
                "correct_index": 1,
                "theme": "async coroutines",
                "hint": "It's two words.",
                "explanation": "`async def` declares a coroutine function.",
            }
        ]
    )
    stub = _StubAIClient(valid_json)
    result = asyncio.run(generate_quiz_questions([_make_section()], "technical", 1, stub))

    assert result == [
        {
            "question": "Which keyword defines a coroutine?",
            "category": "technical",
            "options": ["def", "async def", "coroutine", "await"],
            "correct_index": 1,
            "theme": "async coroutines",
            "hint": "It's two words.",
            "explanation": "`async def` declares a coroutine function.",
        }
    ]


def test_generate_quiz_questions_parses_json_wrapped_in_prose_and_fences():
    messy = (
        "Here you go:\n"
        "```json\n"
        '[{"question": "What is PEP 8?", "category": "technical", '
        '"options": ["A style guide", "A package manager", "A web framework", "A test runner"], '
        '"correct_index": 0, "theme": "pep8", "hint": "It is a style document.", '
        '"explanation": "PEP 8 is the Python style guide."}]\n'
        "```\n"
        "Enjoy!"
    )
    stub = _StubAIClient(messy)
    result = asyncio.run(generate_quiz_questions([_make_section()], "technical", 1, stub))

    assert result[0]["question"] == "What is PEP 8?"
    assert result[0]["correct_index"] == 0


def test_generate_quiz_questions_retries_once_on_malformed_item():
    malformed = json.dumps(
        [{"question": "Bad", "category": "technical", "options": ["only", "two"], "correct_index": 0}]
    )
    good = json.dumps(
        [
            {
                "question": "Good",
                "category": "technical",
                "options": ["a", "b", "c", "d"],
                "correct_index": 2,
                "theme": "general",
                "hint": "A small nudge.",
                "explanation": "A model explanation.",
            }
        ]
    )
    stub = _FlakyJSONAIClient(malformed, good)
    result = asyncio.run(generate_quiz_questions([_make_section()], "technical", 1, stub))

    assert stub.calls == 2
    assert result[0]["question"] == "Good"


def test_generate_questions_accepts_short_response_without_retrying(monkeypatch):
    # A well-formed but short response (fewer items than requested) is
    # accepted as-is, not retried - background pool top-ups intentionally
    # request more than the model may be able to produce from a small
    # knowledge base, and a partial batch is still useful.
    short = json.dumps(
        [
            {
                "question": "Only one",
                "category": "technical",
                "theme": "general",
                "hint": "A nudge.",
                "explanation": "An explanation.",
            }
        ]
    )
    stub = _StubAIClient(short)
    result = asyncio.run(generate_questions([_make_section()], "technical", 2, stub))

    assert stub.calls == 1
    assert len(result) == 1


def test_generate_quiz_questions_fails_gracefully_when_never_valid():
    stub = _FlakyJSONAIClient("not json", "still not json")
    with pytest.raises(AIClientError):
        asyncio.run(generate_quiz_questions([_make_section()], "technical", 1, stub))


def test_generate_questions_defaults_to_english_with_no_language_instruction_needed():
    valid_json = json.dumps(
        [
            {
                "question": "Q1",
                "category": "technical",
                "theme": "general",
                "hint": "A nudge.",
                "explanation": "An explanation.",
            }
        ]
    )
    stub = _RecordingAIClient(valid_json)
    asyncio.run(generate_questions([_make_section()], "technical", 1, stub))

    user_message = stub.messages[1]["content"]
    assert "Write all natural-language text" in user_message
    assert "English" in user_message
    assert '"category" field must still be exactly "technical" or "behavioral" in English' in user_message


def test_generate_questions_includes_ukrainian_language_instruction():
    valid_json = json.dumps(
        [
            {
                "question": "Q1",
                "category": "technical",
                "theme": "general",
                "hint": "A nudge.",
                "explanation": "An explanation.",
            }
        ]
    )
    stub = _RecordingAIClient(valid_json)
    asyncio.run(generate_questions([_make_section()], "technical", 1, stub, language="uk"))

    user_message = stub.messages[1]["content"]
    assert "Ukrainian" in user_message


def test_generate_quiz_questions_includes_russian_language_instruction():
    valid_json = json.dumps(
        [
            {
                "question": "Q1",
                "category": "technical",
                "options": ["a", "b", "c", "d"],
                "correct_index": 0,
                "theme": "general",
                "hint": "A nudge.",
                "explanation": "An explanation.",
            }
        ]
    )
    stub = _RecordingAIClient(valid_json)
    asyncio.run(generate_quiz_questions([_make_section()], "technical", 1, stub, language="ru"))

    user_message = stub.messages[1]["content"]
    assert "Russian" in user_message
