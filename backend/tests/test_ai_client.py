import asyncio

import httpx
import pytest

from app.ai.client import AIClientError, MissingApiKeyError, OpenRouterClient, get_ai_client
from app.models import User
from app.user_api_keys import save_user_api_key


def test_client_retries_on_429_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = OpenRouterClient(
        api_key="test-key",
        model="test-model",
        max_retries=2,
        backoff_base=0.01,
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(client.complete([{"role": "user", "content": "hi"}]))

    assert result == "ok"
    assert calls["n"] == 3


def test_client_raises_after_exhausting_retries_on_429():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    client = OpenRouterClient(
        api_key="test-key",
        model="test-model",
        max_retries=1,
        backoff_base=0.01,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AIClientError):
        asyncio.run(client.complete([{"role": "user", "content": "hi"}]))


def test_client_retries_on_5xx():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = OpenRouterClient(
        api_key="test-key",
        model="test-model",
        max_retries=2,
        backoff_base=0.01,
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(client.complete([{"role": "user", "content": "hi"}]))
    assert result == "ok"


def test_client_raises_when_api_key_missing():
    client = OpenRouterClient(api_key="", model="test-model")

    with pytest.raises(AIClientError):
        asyncio.run(client.complete([{"role": "user", "content": "hi"}]))


def test_client_raises_on_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("connection timed out")

    client = OpenRouterClient(
        api_key="test-key",
        model="test-model",
        max_retries=1,
        backoff_base=0.01,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AIClientError):
        asyncio.run(client.complete([{"role": "user", "content": "hi"}]))


async def _collect(aiter) -> list[str]:
    return [chunk async for chunk in aiter]


def test_stream_complete_yields_text_deltas():
    sse_body = (
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        b"data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})

    client = OpenRouterClient(
        api_key="test-key", model="test-model", transport=httpx.MockTransport(handler)
    )

    chunks = asyncio.run(_collect(client.stream_complete([{"role": "user", "content": "hi"}])))
    assert chunks == ["Hello", " world"]


def test_stream_complete_skips_malformed_lines():
    sse_body = (
        b"data: not-json\n\n"
        b'data: {"choices":[]}\n\n'
        b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
        b"data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body)

    client = OpenRouterClient(
        api_key="test-key", model="test-model", transport=httpx.MockTransport(handler)
    )

    chunks = asyncio.run(_collect(client.stream_complete([{"role": "user", "content": "hi"}])))
    assert chunks == ["ok"]


def test_stream_complete_raises_on_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"server error")

    client = OpenRouterClient(
        api_key="test-key", model="test-model", transport=httpx.MockTransport(handler)
    )

    with pytest.raises(AIClientError):
        asyncio.run(_collect(client.stream_complete([{"role": "user", "content": "hi"}])))


def test_stream_complete_raises_when_api_key_missing():
    client = OpenRouterClient(api_key="", model="test-model")

    with pytest.raises(AIClientError):
        asyncio.run(_collect(client.stream_complete([{"role": "user", "content": "hi"}])))


def test_list_models_returns_parsed_catalog():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "a/1", "name": "Model A", "context_length": 8192},
                    {"id": "a/2", "context_length": None},
                    {"not": "a model"},
                ]
            },
        )

    client = OpenRouterClient(
        api_key="test-key", model="test-model", transport=httpx.MockTransport(handler)
    )
    models = asyncio.run(client.list_models())

    assert models == [
        {"id": "a/1", "name": "Model A", "context_length": 8192},
        {"id": "a/2", "name": "a/2", "context_length": None},
    ]


def test_list_models_raises_on_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = OpenRouterClient(
        api_key="test-key", model="test-model", transport=httpx.MockTransport(handler)
    )

    with pytest.raises(AIClientError):
        asyncio.run(client.list_models())


def test_validate_key_true_on_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"data": {"label": "test"}})

    client = OpenRouterClient(
        api_key="test-key", model="test-model", transport=httpx.MockTransport(handler)
    )
    assert asyncio.run(client.validate_key()) is True


def test_validate_key_false_on_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid"})

    client = OpenRouterClient(
        api_key="bad-key", model="test-model", transport=httpx.MockTransport(handler)
    )
    assert asyncio.run(client.validate_key()) is False


def test_validate_key_false_when_api_key_missing():
    client = OpenRouterClient(api_key="", model="test-model")
    assert asyncio.run(client.validate_key()) is False


def test_get_ai_client_uses_stored_user_key(db_session):
    user = User(email="key-user@example.com", hashed_password="x")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    save_user_api_key(db_session, user.id, "user-secret-key", "user/model")

    client = get_ai_client(current_user=user, db=db_session)

    assert client.api_key == "user-secret-key"
    assert client.model == "user/model"


def test_get_ai_client_has_no_key_without_stored_key(db_session):
    user = User(email="no-key-user@example.com", hashed_password="x")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    client = get_ai_client(current_user=user, db=db_session)

    assert client.api_key == ""


def test_get_ai_client_without_stored_key_raises_on_use(db_session):
    user = User(email="no-key-user-2@example.com", hashed_password="x")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    client = get_ai_client(current_user=user, db=db_session)

    with pytest.raises(MissingApiKeyError):
        asyncio.run(client.complete([{"role": "user", "content": "hi"}]))
