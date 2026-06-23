import asyncio

import httpx

from app.config import settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class AIClientError(Exception):
    """Raised when the AI provider cannot fulfill a request."""


class OpenRouterClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        backoff_base: float = 0.5,
        transport: httpx.BaseTransport | None = None,
    ):
        self.api_key = settings.openrouter_api_key if api_key is None else api_key
        self.model = settings.openrouter_model if model is None else model
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.transport = transport

    async def complete(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        if not self.api_key:
            raise AIClientError("OpenRouter API key is not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {"model": self.model, "messages": messages}
        if temperature is not None:
            payload["temperature"] = temperature

        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as http_client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await http_client.post(OPENROUTER_URL, headers=headers, json=payload)
                except httpx.TimeoutException as exc:
                    if attempt < self.max_retries:
                        await asyncio.sleep(self.backoff_base * (2**attempt))
                        continue
                    raise AIClientError("OpenRouter request timed out") from exc
                except httpx.HTTPError as exc:
                    raise AIClientError(f"OpenRouter request failed: {exc}") from exc

                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < self.max_retries:
                        await asyncio.sleep(self.backoff_base * (2**attempt))
                        continue
                    raise AIClientError(f"OpenRouter returned {response.status_code}")

                if response.status_code >= 400:
                    raise AIClientError(f"OpenRouter returned {response.status_code}: {response.text}")

                data = response.json()
                try:
                    return data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as exc:
                    raise AIClientError("Unexpected OpenRouter response shape") from exc

        raise AIClientError("OpenRouter request failed")


def get_ai_client() -> OpenRouterClient:
    return OpenRouterClient()
