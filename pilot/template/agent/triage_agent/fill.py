"""The fill: what T3 provides for the golden template's fill points, validated (FR-002).

A failing fill raises ``FillError`` naming the fill point, so the build says which part is wrong.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from triage_agent.reference import Reference


class FillError(Exception):
    def __init__(self, part: str, message: str) -> None:
        super().__init__(f"{part}: {message}")
        self.part = part


@dataclass(frozen=True)
class RoutingRules:
    security_keywords: tuple[str, ...]
    category_keywords: dict[str, tuple[str, ...]]
    category_teams: dict[str, str]
    urgency_priority: dict[str, str]
    p1_keywords: tuple[str, ...]


@dataclass(frozen=True)
class Thresholds:
    min_confidence_for_auto: float
    review_on_multi_service: bool


@dataclass(frozen=True)
class Settings:
    token_budget: int
    model_mode: str
    model_name: str


@dataclass(frozen=True)
class Fill:
    instructions: str
    routing: RoutingRules
    tools: frozenset[str]
    thresholds: Thresholds
    settings: Settings


def template_spec(template: Path) -> dict[str, Any]:
    spec: dict[str, Any] = YAML(typ="safe").load((template / "template.yaml").read_text())
    return spec


def _yaml(fill: Path, part: str, file: str) -> Any:
    path = fill / file
    if not path.is_file():
        raise FillError(part, f"{file} is missing")
    try:
        return YAML(typ="safe").load(path.read_text())
    except YAMLError as exc:
        raise FillError(part, f"{file} is not valid YAML ({type(exc).__name__})") from None


def _words(value: Any, part: str, what: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise FillError(part, f"{what} must be a list of words")
    return tuple(v.lower() for v in value)


def _routing(data: Any, categories: set[str], reference: Reference) -> RoutingRules:
    part = "routing_rules"
    if not isinstance(data, Mapping):
        raise FillError(part, "must be a mapping")
    keywords = data.get("category_keywords") or {}
    teams = data.get("category_teams") or {}
    priorities = data.get("priority_rules") or {}
    unknown = sorted((set(keywords) | set(teams)) - categories)
    if unknown:
        raise FillError(part, f"unknown categories {unknown}; allowed {sorted(categories)}")
    missing = sorted(categories - set(teams))
    if missing:
        raise FillError(part, f"category_teams lacks {missing}")
    bad = sorted(t for t in teams.values() if t not in reference.teams)
    if bad:
        raise FillError(part, f"teams {bad} are not in the team directory")
    urgency = priorities.get("urgency") or {}
    if set(urgency) != {"low", "medium", "high"} or not all(
        p in ("P1", "P2", "P3", "P4") for p in urgency.values()
    ):
        raise FillError(part, "priority_rules.urgency maps low, medium and high to P1-P4")
    return RoutingRules(
        security_keywords=_words(data.get("security_keywords"), part, "security_keywords"),
        category_keywords={
            c: _words(w, part, f"category_keywords.{c}") for c, w in keywords.items()
        },
        category_teams={str(c): str(t) for c, t in teams.items()},
        urgency_priority={str(k): str(v) for k, v in urgency.items()},
        p1_keywords=_words(priorities.get("p1_keywords") or [], part, "p1_keywords") or (),
    )


def load_fill(template: Path, fill: Path) -> Fill:
    spec = template_spec(template)
    reference = Reference.load(template)
    points = spec["fill_points"]
    path = fill / points["instructions"]["file"]
    if not path.is_file():
        raise FillError("instructions", f"{path.name} is missing")
    instructions = path.read_text()
    low, high = points["instructions"]["min_length"], points["instructions"]["max_length"]
    if not low <= len(instructions.strip()) <= high or len(instructions) > high:
        raise FillError("instructions", f"must have {low} to {high} characters")

    routing = _routing(
        _yaml(fill, "routing_rules", points["routing_rules"]["file"]),
        set(spec["categories"]),
        reference,
    )

    bindings = _yaml(fill, "tool_bindings", points["tool_bindings"]["file"]) or {}
    tools = bindings.get("tools") if isinstance(bindings, Mapping) else None
    if not isinstance(tools, list) or not tools:
        raise FillError("tool_bindings", "tools must be a non-empty list")
    undeclared = sorted(set(map(str, tools)) - set(spec["tools"]))
    if undeclared:
        raise FillError("tool_bindings", f"tools {undeclared} are not declared by the template")

    raw = _yaml(fill, "thresholds", points["thresholds"]["file"]) or {}
    confidence = raw.get("min_confidence_for_auto") if isinstance(raw, Mapping) else None
    multi = raw.get("review_on_multi_service") if isinstance(raw, Mapping) else None
    if (
        not isinstance(confidence, int | float)
        or isinstance(confidence, bool)
        or not (0 <= confidence <= 1)
    ):
        raise FillError("thresholds", "min_confidence_for_auto must be a number in 0-1")
    if not isinstance(multi, bool):
        raise FillError("thresholds", "review_on_multi_service must be true or false")

    raw = _yaml(fill, "settings", points["settings"]["file"]) or {}
    limits = spec["settings"]
    budget = raw.get("token_budget") if isinstance(raw, Mapping) else None
    mode = raw.get("model_mode") if isinstance(raw, Mapping) else None
    name = raw.get("model_name") if isinstance(raw, Mapping) else None
    if (
        not isinstance(budget, int)
        or not limits["token_budget"]["min"] <= budget <= limits["token_budget"]["max"]
    ):
        raise FillError(
            "settings",
            f"token_budget must be {limits['token_budget']['min']}-{limits['token_budget']['max']}",
        )
    if mode not in limits["model_mode"]:
        raise FillError("settings", f"model_mode must be one of {limits['model_mode']}")
    if not isinstance(name, str) or not name.strip():
        raise FillError("settings", "model_name must be set")

    return Fill(
        instructions=instructions,
        routing=routing,
        tools=frozenset(map(str, tools)),
        thresholds=Thresholds(float(confidence), multi),
        settings=Settings(budget, str(mode), name),
    )
