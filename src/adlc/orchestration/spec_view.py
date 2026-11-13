"""Read-only accessors over one registered terminal spec (the JSON stored by feature 002).

Pure functions, so routing decisions are tested without a database. Nothing here knows a
terminal by name: every value comes from the spec passed in (constitution I).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

Spec = Mapping[str, Any]


def body(spec: Spec) -> Spec:
    """The ``terminal`` mapping of a spec file, or the mapping itself."""
    inner = spec.get("terminal")
    return inner if isinstance(inner, Mapping) else spec


def terminal_id(spec: Spec) -> str:
    return str(body(spec)["metadata"]["id"])


def _section(spec: Spec, *path: str) -> Any:
    node: Any = body(spec)
    for key in path:
        if not isinstance(node, Mapping):
            return None
        node = node.get(key)
    return node


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list | tuple) else []


def triggers(spec: Spec) -> tuple[str, ...]:
    return tuple(str(e) for e in _list(_section(spec, "trigger", "on")))


def trigger_mode(spec: Spec) -> str:
    return str(_section(spec, "trigger", "mode") or "event")


def review_schedule(spec: Spec, risk_tier: str) -> str | None:
    schedule = _section(spec, "trigger", "review_schedule")
    if isinstance(schedule, Mapping):
        value = schedule.get(risk_tier)
        return None if value is None else str(value)
    return None if schedule is None else str(schedule)


@dataclass(frozen=True)
class Check:
    id: str
    expression: str
    blocking: bool
    awaits: str | None = None  # 012: a person's action outside the run this control waits for


def prerequisites(spec: Spec) -> tuple[Check, ...]:
    return tuple(
        Check(str(p["id"]), str(p.get("condition", "")), p.get("on_missing", "block") == "block")
        for p in _list(_section(spec, "prerequisites"))
    )


def prerequisite_entries(spec: Spec) -> tuple[dict[str, Any], ...]:
    """007: each prerequisite as declared (id, description, evidence reference, on_missing)."""
    return tuple(
        {
            "id": str(p["id"]),
            "description": str(p.get("description", "")),
            "evidence_ref": str(p.get("evidence_ref", "")),
            "on_missing": str(p.get("on_missing", "block")),
        }
        for p in _list(_section(spec, "prerequisites"))
    )


def controls(spec: Spec) -> tuple[Check, ...]:
    return tuple(
        Check(
            str(c["id"]),
            str(c.get("rule", "")),
            c.get("severity", "blocking") == "blocking",
            str(c["awaits"]) if c.get("awaits") else None,
        )
        for c in _list(_section(spec, "controls", "automated"))
    )


def checklist_items(spec: Spec) -> tuple[str, ...]:
    return tuple(str(i) for i in _list(_section(spec, "controls", "checklist", "items")))


# Artifacts the platform builds from records; an agent never writes them (011 FR-003, 012 R-09).
BUILT_FORMATS = ("signed_record", "baseline", "gate_summary")


@dataclass(frozen=True)
class ArtifactSpec:
    id: str
    columns: tuple[str, ...]
    condition: str | None
    format: str = "table"
    built_from: Mapping[str, Any] | None = None  # 012: what a ``baseline`` is built from

    @property
    def built(self) -> bool:
        return self.format in BUILT_FORMATS


def artifacts(spec: Spec) -> tuple[ArtifactSpec, ...]:
    out = []
    for a in _list(_section(spec, "evidence", "artifacts")):
        applicability = a.get("applicability") or {}
        condition = (
            applicability.get("when") if applicability.get("mode") == "conditional" else None
        )
        out.append(
            ArtifactSpec(
                str(a["id"]),
                tuple(str(c) for c in _list(a.get("columns"))),
                condition,
                str(a.get("format") or "table"),
                dict(a["built_from"]) if isinstance(a.get("built_from"), Mapping) else None,
            )
        )
    return tuple(out)


def ledger_key(spec: Spec, usecase_id: str, run_version: str) -> str:
    """Render the spec's ledger key. A review period of a continuous terminal is one run, so
    ``${review_period}`` and ``${run_version}`` both name the run (``run-<k>``)."""
    template = str(_section(spec, "evidence", "ledger", "key") or "${usecase_id}/${run_version}")
    key = (
        template.replace("${usecase_id}", usecase_id)
        .replace("${run_version}", run_version)
        .replace("${review_period}", run_version)
    )
    if "${" in key:
        raise ValueError(f"unresolved variable in ledger key template {template!r}")
    return key


@dataclass(frozen=True)
class HumanRole:
    role: str
    raci: str
    scope: str | None


def human_roles(spec: Spec) -> tuple[HumanRole, ...]:
    return tuple(
        HumanRole(str(r["role"]), str(r.get("raci", "")), r.get("scope"))
        for r in _list(_section(spec, "actors", "human_roles"))
    )


def accountable_roles(spec: Spec) -> frozenset[str]:
    return frozenset(r.role for r in human_roles(spec) if r.raci == "A")


def default_addressee(spec: Spec) -> str | None:
    """FR-023a: the R role, else the whole-terminal A role, else the first A role in spec order."""
    roles = human_roles(spec)
    candidates = (
        [r for r in roles if r.raci == "R"]
        or [r for r in roles if r.raci == "A" and r.scope is None]
        or [r for r in roles if r.raci == "A"]
    )
    return candidates[0].role if candidates else None


@dataclass(frozen=True)
class PlusApprover:
    role: str
    condition: str


@dataclass(frozen=True)
class SignOffRule:
    roles: frozenset[str]
    min_approvers: int
    plus: tuple[PlusApprover, ...] = ()
    board: str | None = None
    external: str | None = None
    external_when: str | None = None


def sign_off_rule(spec: Spec, risk_tier: str, mode: str) -> SignOffRule:
    """FR-009b: the plain rule, or ``by_tier[<tier>]``, or ``by_mode[<mode>]``."""
    raw = _section(spec, "authorities", "sign_off") or {}
    if isinstance(raw.get("by_tier"), Mapping):
        raw = raw["by_tier"].get(risk_tier) or {}
    elif isinstance(raw.get("by_mode"), Mapping):
        raw = raw["by_mode"].get(mode) or {}
    external = raw.get("external")
    return SignOffRule(
        roles=frozenset(str(r) for r in _list(raw.get("roles"))),
        min_approvers=int(raw.get("min_approvers", 1)),
        plus=tuple(
            PlusApprover(str(p["role"]), str(p.get("when", "true"))) for p in _list(raw.get("plus"))
        ),
        board=None if raw.get("board") is None else str(raw["board"]),
        external=None if not isinstance(external, Mapping) else str(external.get("body")),
        external_when=None
        if not isinstance(external, Mapping) or external.get("when") is None
        else str(external["when"]),
    )


def outcome(spec: Spec, status: str) -> Mapping[str, Any]:
    value = _section(spec, "outcome_model", status)
    return value if isinstance(value, Mapping) else {}


def outcome_requires(spec: Spec, status: str) -> tuple[str, ...]:
    return tuple(str(r) for r in _list(outcome(spec, status).get("requires")))


def outcome_set_by(spec: Spec, status: str) -> frozenset[str]:
    return frozenset(str(r) for r in _list(outcome(spec, status).get("set_by")))


def outcome_not_allowed(spec: Spec, status: str) -> bool:
    return bool(outcome(spec, status).get("not_allowed"))


def emits(spec: Spec) -> tuple[str, ...]:
    return tuple(str(e) for e in _list(outcome(spec, "pass").get("emits")))


def rework_causes(spec: Spec) -> tuple[str, ...]:
    by_cause = outcome(spec, "rework").get("route_by_root_cause")
    return tuple(str(c) for c in by_cause) if isinstance(by_cause, Mapping) else ()


def reentry_terminals(spec: Spec) -> frozenset[str]:
    classes = _section(spec, "change_classes")
    if not isinstance(classes, Mapping):
        return frozenset()
    return frozenset(
        str(c["reentry"]) for c in classes.values() if isinstance(c, Mapping) and c.get("reentry")
    )


def raised_events(spec: Spec) -> frozenset[str]:
    return frozenset(str(m["raises"]) for m in _list(_section(spec, "monitors")) if m.get("raises"))


def status_rights(spec: Spec, actor: str) -> frozenset[str]:
    rights = _section(spec, "authorities", "status_rights") or {}
    return frozenset(str(r) for r in _list(rights.get(actor)))
