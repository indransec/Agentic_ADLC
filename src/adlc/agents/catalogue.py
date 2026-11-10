"""Model and agent catalogues as the runtime reads them (006 research R-04, R-05a, R-16).

Both come from the spec registry (validated by the 002 toolkit). No model, provider or agent name
is written in this module (constitution I).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from adlc.spec_toolkit.registry import SpecRegistry

MILLION = Decimal(1_000_000)
CENT_FRACTION = Decimal("0.000001")
CHARS_PER_TOKEN = 4  # conservative estimate when a provider's tokenizer is not at hand


class UnknownProfile(Exception):
    pass


class UnknownAgent(Exception):
    pass


def estimate_tokens(text: str) -> int:
    """A rough token count used only to decide whether a request fits a context window."""
    return -(-len(text) // CHARS_PER_TOKEN)


def _price(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


@dataclass(frozen=True)
class ModelEntry:
    provider: str
    model: str
    input_per_mtok: Decimal | None
    output_per_mtok: Decimal | None
    max_output_tokens: int
    context_tokens: int
    max_data_class: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def cost(self, tokens_in: int, tokens_out: int) -> Decimal | None:
        """USD for one call; None when a price is unknown (never zero by default, FR-021)."""
        if self.input_per_mtok is None or self.output_per_mtok is None:
            return None
        raw = (tokens_in * self.input_per_mtok + tokens_out * self.output_per_mtok) / MILLION
        return raw.quantize(CENT_FRACTION, rounding=ROUND_HALF_UP)

    def fits(self, request_tokens: int) -> bool:
        return request_tokens <= self.context_tokens

    def capped(self, max_tokens: int) -> int:
        return min(max_tokens, self.max_output_tokens)


@dataclass(frozen=True)
class ModelCatalogue:
    profile: str
    tiers: Mapping[str, tuple[ModelEntry, ...]]
    data_class_rank: Mapping[str, int]

    @classmethod
    def from_content(
        cls, content: Mapping[str, Any], profile: str, data_class_rank: Mapping[str, int]
    ) -> "ModelCatalogue":
        profiles = content.get("profiles") or {}
        if profile not in profiles:
            raise UnknownProfile(
                f"model catalogue profile {profile!r} not found; known: {sorted(profiles)}"
            )
        tiers = {
            tier: tuple(
                ModelEntry(
                    provider=str(e["provider"]),
                    model=str(e["model"]),
                    input_per_mtok=_price(e.get("input_per_mtok")),
                    output_per_mtok=_price(e.get("output_per_mtok")),
                    max_output_tokens=int(e["max_output_tokens"]),
                    context_tokens=int(e["context_tokens"]),
                    max_data_class=str(e["max_data_class"]),
                    params=dict(e.get("params") or {}),
                )
                for e in entries
            )
            for tier, entries in profiles[profile].items()
        }
        return cls(profile, tiers, dict(data_class_rank))

    def entries(self, tier: str) -> tuple[ModelEntry, ...]:
        return self.tiers[tier]

    def allows(self, entry: ModelEntry, ceiling: str) -> bool:
        """The model is approved at least up to the run's data ceiling (FR-005).

        A ceiling that is unknown or still a resolver counts as above every rank (fails closed).
        """
        ceiling_rank = self.data_class_rank.get(ceiling, max(self.data_class_rank.values()) + 1)
        return self.data_class_rank.get(entry.max_data_class, 0) >= ceiling_rank


@dataclass(frozen=True)
class ToolBinding:
    tool: str
    permission: str

    @property
    def action(self) -> str:
        return self.permission.partition(":")[0]

    @property
    def resource(self) -> str:
        return self.permission.partition(":")[2]


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    version: str
    implementation: str  # stub | model
    model_tier: str
    prompt: tuple[str, str] | None
    tools: tuple[ToolBinding, ...] = ()

    def tool(self, name: str) -> ToolBinding | None:
        return next((t for t in self.tools if t.tool == name), None)


@dataclass(frozen=True)
class AgentCatalogue:
    agents: Mapping[str, AgentDefinition]

    @classmethod
    def from_content(cls, content: Mapping[str, Any]) -> "AgentCatalogue":
        agents: dict[str, AgentDefinition] = {}
        for a in content.get("agents") or []:
            prompt = a.get("prompt")
            agents[str(a["id"])] = AgentDefinition(
                id=str(a["id"]),
                version=str(a["version"]),
                implementation=str(a["implementation"]),
                model_tier=str(a["model_tier"]),
                prompt=None if not prompt else (str(prompt["id"]), str(prompt["version"])),
                tools=tuple(
                    ToolBinding(str(t["tool"]), str(t["permission"])) for t in a.get("tools") or []
                ),
            )
        return cls(agents)

    def agent(self, agent_id: str) -> AgentDefinition:
        try:
            return self.agents[agent_id]
        except KeyError:
            raise UnknownAgent(f"agent {agent_id} is not in the agents catalogue") from None

    def model_agents(self) -> Sequence[AgentDefinition]:
        return [a for a in self.agents.values() if a.implementation == "model"]


def _rank(registry: SpecRegistry) -> dict[str, int]:
    entry = registry.catalogue("data_classes")
    content = {} if entry is None else entry.content
    return {str(d["id"]): int(d["rank"]) for d in content.get("data_classes") or []}


def load_catalogues(registry: SpecRegistry, profile: str) -> tuple[ModelCatalogue, AgentCatalogue]:
    models = registry.catalogue("model_catalogue")
    agents = registry.catalogue("agents")
    if models is None or agents is None:
        raise UnknownProfile("model_catalogue and agents catalogues are not registered")
    return (
        ModelCatalogue.from_content(models.content, profile, _rank(registry)),
        AgentCatalogue.from_content(agents.content),
    )
