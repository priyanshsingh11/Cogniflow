"""Scripted fake LLM provider for deterministic gateway tests."""

from app.llm.base import Provider
from app.llm.errors import LLMError
from app.llm.types import LLMResponse, Message


class FakeProvider(Provider):
    """script maps model id -> list of outcomes consumed in order.
    An outcome is either a string (returned as content) or an LLMError
    instance (raised). The last outcome repeats once the list is exhausted."""

    def __init__(self, name: str, script: dict[str, list[str | LLMError]]) -> None:
        self.name = name
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[str] = []

    async def chat(self, model: str, messages: list[Message], **params) -> LLMResponse:
        self.calls.append(model)
        outcomes = self.script.get(model, ["ok"])
        outcome = outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]
        if isinstance(outcome, LLMError):
            raise outcome
        return LLMResponse(
            content=outcome,
            provider=self.name,
            model=model,
            prompt_tokens=10,
            completion_tokens=5,
            latency_ms=1,
        )
