import uuid
from dataclasses import dataclass, field

from app.llm.types import ModelRef, RoutingHints, Tier

# Which router step_type each agent role maps to (see app/llm/router.py).
ROLE_STEP_TYPE = {
    "research": "research",  # default -> medium tier
    "analysis": "analyze",  # -> large
    "writing": "write",  # default -> medium
    "review": "review",  # -> large
}
ROLES = (*ROLE_STEP_TYPE, "custom")


@dataclass
class AgentConfig:
    """Everything the runtime needs about an agent, from a DB row or a built-in."""

    name: str
    role: str
    system_prompt: str
    tier_pin: str | None = None
    model_pin: str | None = None
    params: dict = field(default_factory=dict)
    id: uuid.UUID | None = None  # None for built-in (unsaved) specialists

    def routing_hints(self, num_documents: int = 0) -> RoutingHints:
        return RoutingHints(
            step_type=ROLE_STEP_TYPE.get(self.role),
            num_documents=num_documents,
            pinned_tier=Tier(self.tier_pin) if self.tier_pin else None,
            pinned_model=ModelRef.parse(self.model_pin) if self.model_pin else None,
            params=dict(self.params),
        )

    @classmethod
    def from_row(cls, row) -> "AgentConfig":
        return cls(
            id=row.id,
            name=row.name,
            role=row.role,
            system_prompt=row.system_prompt,
            tier_pin=row.tier_pin,
            model_pin=row.model_pin,
            params=row.params or {},
        )
