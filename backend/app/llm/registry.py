from dataclasses import dataclass
from pathlib import Path

import yaml

from app.llm.types import ModelRef, Tier

DEFAULT_MODELS_PATH = Path(__file__).parent / "models.yaml"
_TIER_ORDER = [Tier.SMALL, Tier.MEDIUM, Tier.LARGE]


@dataclass
class ModelRegistry:
    tiers: dict[Tier, list[ModelRef]]
    last_resort: list[ModelRef]

    @classmethod
    def load(cls, path: Path = DEFAULT_MODELS_PATH) -> "ModelRegistry":
        raw = yaml.safe_load(path.read_text())
        tiers = {
            Tier(name): [ModelRef.parse(v) for v in refs] for name, refs in raw["tiers"].items()
        }
        missing = [t.value for t in _TIER_ORDER if not tiers.get(t)]
        if missing:
            raise ValueError(f"models.yaml has no models for tier(s): {missing}")
        last_resort = [ModelRef.parse(v) for v in raw.get("last_resort", [])]
        return cls(tiers=tiers, last_resort=last_resort)

    def chain(self, start: Tier) -> list[tuple[str, ModelRef]]:
        """Ordered (tier label, model) attempts: start tier, then each higher
        tier, then last_resort. Escalation never goes down."""
        chain: list[tuple[str, ModelRef]] = []
        for tier in _TIER_ORDER:
            if tier.rank >= start.rank:
                chain.extend((tier.value, ref) for ref in self.tiers[tier])
        chain.extend(("last_resort", ref) for ref in self.last_resort)
        return chain
