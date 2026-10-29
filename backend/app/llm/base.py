from abc import ABC, abstractmethod

from app.llm.types import LLMResponse, Message


class Provider(ABC):
    """One LLM vendor. Adapters translate to/from the vendor's HTTP API and
    raise the errors in app.llm.errors; they never retry or fall back."""

    name: str

    @abstractmethod
    async def chat(self, model: str, messages: list[Message], **params) -> LLMResponse: ...

    async def close(self) -> None:  # pragma: no cover - default no-op
        return None
