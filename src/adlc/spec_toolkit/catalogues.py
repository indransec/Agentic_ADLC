"""Typed, read-only views over the shared catalogues (FR-004).

Rules read names from these views, never from constants in code (constitution I).
Missing or broken catalogues give empty views; their problems are reported by L1/L2.
"""

from dataclasses import dataclass, field
from typing import Any

from adlc.spec_toolkit.loader import SpecBundle


@dataclass(frozen=True)
class Param:
    name: str
    kind: str


@dataclass(frozen=True)
class Predicate:
    name: str
    params: tuple[Param, ...]
    returns: str


@dataclass(frozen=True)
class Metric:
    name: str
    metric_class: str
    unit: str
    direction: str


@dataclass(frozen=True)
class Guardrail:
    name: str
    unit: str
    direction: str
    tighten_only: bool
    monotonic: bool
    values: dict[str, Any]
    proposed_default: bool


def _entries(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key)
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


@dataclass(frozen=True)
class Catalogues:
    role_ids: frozenset[str] = frozenset()
    risk_tier_rank: dict[str, int] = field(default_factory=dict)
    event_patterns: tuple[str, ...] = ()
    external_events: frozenset[str] = frozenset()
    operational_events: frozenset[str] = frozenset()
    root_causes: frozenset[str] = frozenset()
    change_class_rank: dict[str, int] = field(default_factory=dict)
    data_class_rank: dict[str, int] = field(default_factory=dict)
    data_class_resolvers: frozenset[str] = frozenset()
    model_tiers: frozenset[str] = frozenset()
    mcp_scopes: dict[str, frozenset[str]] = field(default_factory=dict)
    permission_verbs: frozenset[str] = frozenset()
    duty_groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    evidence_sources: dict[str, frozenset[str]] = field(default_factory=dict)
    route_destinations: dict[str, str] = field(default_factory=dict)
    predicates: dict[str, Predicate] = field(default_factory=dict)
    metrics: dict[str, Metric] = field(default_factory=dict)
    guardrails: dict[str, Guardrail] = field(default_factory=dict)

    @property
    def change_classes(self) -> frozenset[str]:
        return frozenset(self.change_class_rank)

    @property
    def data_classes(self) -> frozenset[str]:
        return frozenset(self.data_class_rank)

    @property
    def risk_tiers(self) -> frozenset[str]:
        return frozenset(self.risk_tier_rank)

    @property
    def terminal_record_fields(self) -> frozenset[str]:
        return self.evidence_sources.get("terminal_record", frozenset())

    @classmethod
    def from_bundle(cls, bundle: SpecBundle) -> "Catalogues":
        c = bundle.catalogue_data

        def ids(name: str, key: str | None = None) -> frozenset[str]:
            return frozenset(str(e["id"]) for e in _entries(c(name), key or name) if "id" in e)

        def ranks(name: str) -> dict[str, int]:
            return {
                str(e["id"]): int(e.get("rank", 0)) for e in _entries(c(name), name) if "id" in e
            }

        perms = c("permissions")
        groups = perms.get("duty_groups")
        return cls(
            role_ids=ids("roles"),
            risk_tier_rank=ranks("risk_tiers"),
            event_patterns=tuple(
                str(e["pattern"]) for e in _entries(c("events"), "patterns") if "pattern" in e
            ),
            external_events=ids("events", "external"),
            operational_events=ids("events", "operational"),
            root_causes=ids("root_causes"),
            change_class_rank=ranks("change_classes"),
            data_class_rank=ranks("data_classes"),
            data_class_resolvers=ids("data_classes", "resolvers"),
            model_tiers=ids("model_tiers"),
            mcp_scopes={
                str(e["id"]): frozenset(str(s) for s in e.get("scopes", []))
                for e in _entries(c("mcp_servers"), "mcp_servers")
                if "id" in e
            },
            permission_verbs=frozenset(str(v) for v in perms.get("verbs", []) or []),
            duty_groups={
                str(k): tuple(str(p) for p in v)
                for k, v in (groups.items() if isinstance(groups, dict) else [])
                if isinstance(v, list)
            },
            evidence_sources={
                str(e["id"]): frozenset(str(f) for f in e.get("fields", []))
                for e in _entries(c("evidence_sources"), "evidence_sources")
                if "id" in e
            },
            route_destinations={
                str(e["id"]): str(e.get("kind", ""))
                for e in _entries(c("route_destinations"), "route_destinations")
                if "id" in e
            },
            predicates={
                str(e["name"]): Predicate(
                    name=str(e["name"]),
                    params=tuple(
                        Param(str(p.get("name")), str(p.get("kind")))
                        for p in e.get("params", [])
                        if isinstance(p, dict)
                    ),
                    returns=str(e.get("returns", "bool")),
                )
                for e in _entries(c("predicates"), "predicates")
                if "name" in e
            },
            metrics={
                str(e["name"]): Metric(
                    str(e["name"]), str(e.get("class")), str(e.get("unit")), str(e.get("direction"))
                )
                for e in _entries(c("metrics"), "metrics")
                if "name" in e
            },
            guardrails={
                str(e["name"]): Guardrail(
                    name=str(e["name"]),
                    unit=str(e.get("unit")),
                    direction=str(e.get("direction")),
                    tighten_only=bool(e.get("tighten_only", False)),
                    monotonic=bool(e.get("monotonic", True)),
                    values=dict(e.get("values") or {}),
                    proposed_default=bool(e.get("proposed_default", False)),
                )
                for e in _entries(c("guardrails"), "guardrails")
                if "name" in e
            },
        )
