import asyncio
import json

import pytest

from app.ai.client import AIClientError, get_ai_client
from app.ai.evaluate import (
    _coerce_score,
    _parse_stream_evaluation,
    evaluate_answer,
    evaluate_answer_stream,
)
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


def test_parse_stream_evaluation_parses_well_formed_text():
    raw = (
        "SCORE: 9\n"
        "FEEDBACK: Excellent.\n"
        "STRENGTHS:\n"
        "- thorough\n"
        "- accurate\n"
        "GAPS:\n"
        "- (none)\n"
    )
    assert _parse_stream_evaluation(raw) == {
        "score": 9,
        "feedback": "Excellent.",
        "strengths": ["thorough", "accurate"],
        "gaps": [],
    }


def test_parse_stream_evaluation_returns_none_without_score_line():
    assert _parse_stream_evaluation("just some prose with no structure") is None


class _StubStreamingAIClient:
    def __init__(self, chunks: list[str], fallback_response: str | None = None):
        self.chunks = chunks
        self.fallback_response = fallback_response
        self.complete_calls = 0
        self.messages: list[dict[str, str]] | None = None

    async def stream_complete(self, messages, temperature=None):
        self.messages = messages
        for chunk in self.chunks:
            yield chunk

    async def complete(self, messages, temperature=None):
        self.complete_calls += 1
        return self.fallback_response or ""


async def _run_stream(stub, language: str = "en"):
    deltas = []
    result = None
    async for delta, evaluation in evaluate_answer_stream("Q", "A", "context", stub, language=language):
        if delta is not None:
            deltas.append(delta)
        if evaluation is not None:
            result = evaluation
    return deltas, result


def test_evaluate_answer_stream_yields_deltas_then_final_result():
    chunks = ["SCORE: 7\n", "FEEDBACK: Good answer.\n", "STRENGTHS:\n- clear\nGAPS:\n- depth\n"]
    stub = _StubStreamingAIClient(chunks)

    deltas, result = asyncio.run(_run_stream(stub))

    assert deltas == chunks
    assert result == {"score": 7, "feedback": "Good answer.", "strengths": ["clear"], "gaps": ["depth"]}


def test_evaluate_answer_stream_falls_back_to_non_streamed_retry_on_malformed_output():
    stub = _StubStreamingAIClient(
        chunks=["this is not the right format at all"],
        fallback_response="SCORE: 3\nFEEDBACK: Retry worked.\nSTRENGTHS:\n- (none)\nGAPS:\n- (none)\n",
    )

    _, result = asyncio.run(_run_stream(stub))

    assert result == {"score": 3, "feedback": "Retry worked.", "strengths": [], "gaps": []}
    assert stub.complete_calls == 1


def test_evaluate_answer_stream_raises_when_unparseable_even_after_retry():
    stub = _StubStreamingAIClient(chunks=["garbage"], fallback_response="still garbage")

    with pytest.raises(AIClientError):
        asyncio.run(_run_stream(stub))


def test_evaluate_answer_defaults_to_english_language_instruction():
    response = json.dumps({"score": 5, "feedback": "x", "strengths": [], "gaps": []})
    stub = _RecordingAIClient(response)
    asyncio.run(evaluate_answer("Q", "A", "context", stub))

    user_message = stub.messages[1]["content"]
    assert "Write the feedback text" in user_message
    assert "English" in user_message


def test_evaluate_answer_includes_ukrainian_language_instruction():
    response = json.dumps({"score": 5, "feedback": "x", "strengths": [], "gaps": []})
    stub = _RecordingAIClient(response)
    asyncio.run(evaluate_answer("Q", "A", "context", stub, language="uk"))

    user_message = stub.messages[1]["content"]
    assert "Ukrainian" in user_message


def test_evaluate_answer_stream_includes_russian_language_instruction_but_keeps_labels_english():
    chunks = ["SCORE: 7\n", "FEEDBACK: Good answer.\n", "STRENGTHS:\n- clear\nGAPS:\n- depth\n"]
    stub = _StubStreamingAIClient(chunks)

    asyncio.run(_run_stream(stub, language="ru"))

    user_message = stub.messages[1]["content"]
    assert "Russian" in user_message
    assert '"SCORE:"/"FEEDBACK:"/"STRENGTHS:"/"GAPS:"' in user_message
