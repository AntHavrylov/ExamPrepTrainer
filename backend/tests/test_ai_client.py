import asyncio

import httpx
import pytest

from app.ai.client import AIClientError, OpenRouterClient


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
