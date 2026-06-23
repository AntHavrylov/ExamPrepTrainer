import json

from app.ai.client import get_ai_client
from app.ai.evaluate import _coerce_score
from app.main import app


class _StubAIClient:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls = 0
        self.last_temperature = None

    async def complete(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        self.calls += 1
        self.last_temperature = temperature
        return self.response_text


def _override_ai_client(stub) -> None:
    app.dependency_overrides[get_ai_client] = lambda: stub


def _clear_ai_override() -> None:
    app.dependency_overrides.pop(get_ai_client, None)


def test_evaluate_weak_answer_returns_low_score_with_gaps(client, make_user):
    headers = make_user("eval-weak@example.com")
    weak_response = json.dumps(
        {
            "score": 2,
            "feedback": "The answer misses key concepts.",
            "strengths": [],
            "gaps": ["Did not mention the GIL", "No discussion of asyncio"],
        }
    )
    stub = _StubAIClient(weak_response)
    _override_ai_client(stub)
    try:
        response = client.post(
            "/ai/evaluate",
            json={"question": "Explain the GIL.", "answer": "I don't know.", "section_ids": []},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    assert response.status_code == 200
    body = response.json()
    assert body["score"] <= 4
    assert len(body["gaps"]) > 0
    assert stub.last_temperature == 0.0


def test_evaluate_strong_answer_returns_high_score_with_strengths(client, make_user):
    headers = make_user("eval-strong@example.com")
    strong_response = json.dumps(
        {
            "score": 9,
            "feedback": "Excellent, thorough answer.",
            "strengths": [
                "Clear explanation of the GIL",
                "Correctly contrasts threading vs multiprocessing",
            ],
            "gaps": [],
        }
    )
    _override_ai_client(_StubAIClient(strong_response))
    try:
        response = client.post(
            "/ai/evaluate",
            json={
                "question": "Explain the GIL.",
                "answer": "Detailed, accurate, well-structured answer covering the GIL in depth.",
                "section_ids": [],
            },
            headers=headers,
        )
    finally:
        _clear_ai_override()

    assert response.status_code == 200
    body = response.json()
    assert body["score"] >= 7
    assert len(body["strengths"]) > 0


def test_evaluate_score_above_range_is_clamped_to_10(client, make_user):
    headers = make_user("eval-clamp-high@example.com")
    out_of_range = json.dumps({"score": 137, "feedback": "x", "strengths": [], "gaps": []})
    _override_ai_client(_StubAIClient(out_of_range))
    try:
        response = client.post(
            "/ai/evaluate",
            json={"question": "Q", "answer": "A", "section_ids": []},
            headers=headers,
        )
    finally:
        _clear_ai_override()
    assert response.json()["score"] == 10


def test_evaluate_score_below_range_is_clamped_to_0(client, make_user):
    headers = make_user("eval-clamp-low@example.com")
    out_of_range = json.dumps({"score": -8, "feedback": "x", "strengths": [], "gaps": []})
    _override_ai_client(_StubAIClient(out_of_range))
    try:
        response = client.post(
            "/ai/evaluate",
            json={"question": "Q", "answer": "A", "section_ids": []},
            headers=headers,
        )
    finally:
        _clear_ai_override()
    assert response.json()["score"] == 0


def test_evaluate_non_numeric_score_coerced_to_zero(client, make_user):
    headers = make_user("eval-nonnumeric@example.com")
    non_numeric = json.dumps({"score": "great job", "feedback": "x", "strengths": [], "gaps": []})
    _override_ai_client(_StubAIClient(non_numeric))
    try:
        response = client.post(
            "/ai/evaluate",
            json={"question": "Q", "answer": "A", "section_ids": []},
            headers=headers,
        )
    finally:
        _clear_ai_override()
    assert response.json()["score"] == 0


def test_evaluate_parses_json_wrapped_in_prose_and_fences(client, make_user):
    headers = make_user("eval-messy@example.com")
    messy = (
        "Here is my evaluation:\n"
        "```json\n"
        '{"score": 6, "feedback": "Decent.", "strengths": ["clear"], "gaps": ["depth"]}\n'
        "```\n"
        "Hope that helps!"
    )
    _override_ai_client(_StubAIClient(messy))
    try:
        response = client.post(
            "/ai/evaluate",
            json={"question": "Q", "answer": "A", "section_ids": []},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    assert response.status_code == 200
    assert response.json() == {
        "score": 6,
        "feedback": "Decent.",
        "strengths": ["clear"],
        "gaps": ["depth"],
    }


def test_evaluate_rejects_another_users_section(client, make_user):
    headers_a = make_user("eval-a@example.com")
    headers_b = make_user("eval-b@example.com")
    section = client.post("/sections", json={"name": "Secret"}, headers=headers_a).json()

    _override_ai_client(
        _StubAIClient(json.dumps({"score": 5, "feedback": "x", "strengths": [], "gaps": []}))
    )
    try:
        response = client.post(
            "/ai/evaluate",
            json={"question": "Q", "answer": "A", "section_ids": [section["id"]]},
            headers=headers_b,
        )
    finally:
        _clear_ai_override()
    assert response.status_code in (403, 404)


def test_coerce_score_clamps_and_rounds():
    assert _coerce_score(15) == 10
    assert _coerce_score(-5) == 0
    assert _coerce_score(7.6) == 8
    assert _coerce_score("not a number") == 0
    assert _coerce_score(None) == 0
