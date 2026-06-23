import json

import pytest
from fastapi import HTTPException

from app.ai.client import get_ai_client
from app.config import settings
from app.main import app
from app.rate_limit import _hits, check_ai_rate_limit


@pytest.fixture(autouse=True)
def _clear_rate_limit_buckets():
    _hits.clear()
    yield
    _hits.clear()


def test_check_ai_rate_limit_allows_up_to_the_max(monkeypatch):
    monkeypatch.setattr(settings, "ai_rate_limit_max_requests", 3)
    monkeypatch.setattr(settings, "ai_rate_limit_window_seconds", 60)

    for _ in range(3):
        check_ai_rate_limit(user_id=1)

    with pytest.raises(HTTPException) as exc_info:
        check_ai_rate_limit(user_id=1)
    assert exc_info.value.status_code == 429


def test_check_ai_rate_limit_is_per_user(monkeypatch):
    monkeypatch.setattr(settings, "ai_rate_limit_max_requests", 1)
    monkeypatch.setattr(settings, "ai_rate_limit_window_seconds", 60)

    check_ai_rate_limit(user_id=1)
    check_ai_rate_limit(user_id=2)  # different user, separate bucket

    with pytest.raises(HTTPException):
        check_ai_rate_limit(user_id=1)


def test_check_ai_rate_limit_resets_after_window_expires(monkeypatch):
    monkeypatch.setattr(settings, "ai_rate_limit_max_requests", 1)
    monkeypatch.setattr(settings, "ai_rate_limit_window_seconds", 60)

    check_ai_rate_limit(user_id=1)
    bucket = _hits[1]
    bucket[0] -= 61  # simulate the window having elapsed

    check_ai_rate_limit(user_id=1)  # should succeed again, old hit expired


class _StubAIClient:
    async def complete(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        return json.dumps({"score": 5, "feedback": "ok", "strengths": [], "gaps": []})


def test_generate_endpoint_returns_429_when_limit_exceeded(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "ai_rate_limit_max_requests", 1)
    headers = make_user("rate-generate@example.com")
    section = client.post("/sections", json={"name": "Python"}, headers=headers).json()

    app.dependency_overrides[get_ai_client] = lambda: _StubAIClient()
    try:
        first = client.post(
            "/ai/generate",
            json={"section_ids": [section["id"]], "mode": "technical", "count": 1},
            headers=headers,
        )
        second = client.post(
            "/ai/generate",
            json={"section_ids": [section["id"]], "mode": "technical", "count": 1},
            headers=headers,
        )
    finally:
        del app.dependency_overrides[get_ai_client]

    assert first.status_code in (200, 503)
    assert second.status_code == 429


def test_evaluate_endpoint_returns_429_when_limit_exceeded(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "ai_rate_limit_max_requests", 1)
    headers = make_user("rate-evaluate@example.com")

    app.dependency_overrides[get_ai_client] = lambda: _StubAIClient()
    try:
        first = client.post(
            "/ai/evaluate",
            json={"question": "Q", "answer": "A", "section_ids": []},
            headers=headers,
        )
        second = client.post(
            "/ai/evaluate",
            json={"question": "Q", "answer": "A", "section_ids": []},
            headers=headers,
        )
    finally:
        del app.dependency_overrides[get_ai_client]

    assert first.status_code == 200
    assert second.status_code == 429
