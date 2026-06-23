from app.ai.client import AIClientError, get_ai_client
from app.main import app


class _StubAIClient:
    async def complete(self, messages: list[dict[str, str]]) -> str:
        return "Hello!"


class _RateLimitedAIClient:
    async def complete(self, messages: list[dict[str, str]]) -> str:
        raise AIClientError("OpenRouter returned 429")


def test_ping_requires_authentication(client):
    response = client.get("/ai/ping")
    assert response.status_code == 401


def test_ping_returns_canned_response_with_mocked_client(client, make_user):
    headers = make_user("ai-ping@example.com")
    app.dependency_overrides[get_ai_client] = lambda: _StubAIClient()
    try:
        response = client.get("/ai/ping", headers=headers)
    finally:
        del app.dependency_overrides[get_ai_client]

    assert response.status_code == 200
    assert response.json() == {"response": "Hello!"}


def test_ping_handles_rate_limit_gracefully(client, make_user):
    headers = make_user("ai-ratelimit@example.com")
    app.dependency_overrides[get_ai_client] = lambda: _RateLimitedAIClient()
    try:
        response = client.get("/ai/ping", headers=headers)
    finally:
        del app.dependency_overrides[get_ai_client]

    assert response.status_code == 503
