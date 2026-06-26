from collections.abc import AsyncIterator
from typing import Protocol, TypedDict


class ModelInfo(TypedDict):
    id: str
    name: str
    context_length: int | None


class AIProvider(Protocol):
    """Capabilities a chat-completion provider must offer.

    OpenRouter is the only implementation today; this exists so a future
    "choose your provider" feature can add another implementation without
    changing call sites.
    """

    api_key: str  # empty string when no key is configured

    async def list_models(self) -> list[ModelInfo]: ...

    async def validate_key(self) -> bool: ...

    async def complete(
        self, messages: list[dict[str, str]], temperature: float | None = None
    ) -> str: ...

    def stream_complete(
        self, messages: list[dict[str, str]], temperature: float | None = None
    ) -> AsyncIterator[str]: ...
