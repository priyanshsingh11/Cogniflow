import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class Tier(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"

    @property
    def rank(self) -> int:
        return {"small": 0, "medium": 1, "large": 2}[self.value]


@dataclass(frozen=True)
class Message:
    role: str  # system | user | assistant
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class ModelRef:
    provider: str
    model: str

    @classmethod
    def parse(cls, value: str) -> "ModelRef":
        """'groq:openai/gpt-oss-20b' -> ModelRef. Split on the FIRST colon only,
        because OpenRouter ids contain their own ':free' suffix."""
        provider, _, model = value.partition(":")
        if not provider or not model:
            raise ValueError(f"model ref must look like 'provider:model', got {value!r}")
        return cls(provider, model)


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0


@dataclass
class RoutingHints:
    """Inputs to the rules-based router. All optional."""

    step_type: str | None = None  # e.g. classify | extract | plan | analyze | review
    num_documents: int = 0  # retrieved passages/documents feeding the prompt
    pinned_tier: Tier | None = None  # per-agent override
    pinned_model: ModelRef | None = None  # per-agent override (tried first)
    params: dict = field(default_factory=dict)  # temperature, max_tokens, ...


@dataclass
class Attempt:
    """One model call (or skip). Becomes one llm_calls row."""

    attempt_no: int
    tier: str  # small | medium | large | last_resort | pinned
    provider: str
    model: str
    status: str  # success | error | invalid_output | skipped_rate_limit
    error_type: str | None = None
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    route_reason: str = ""  # set by the gateway for every attempt of a call
    agent_id: uuid.UUID | None = None  # set by the agent runtime


@dataclass
class GatewayResult:
    response: LLMResponse
    tier: str
    route_reason: str
    attempts: list[Attempt]
