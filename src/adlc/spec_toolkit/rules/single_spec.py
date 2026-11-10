"""L3 rules: checks inside one terminal spec (contracts/validation-rules.md).

Also provides walkers used by L4 rules: every expression and every evidence reference in a
spec, with its JSON pointer. Nothing here names a terminal (constitution I).
"""

import re
from collections import Counter
from collections.abc import Iterator
from typing import Any

from adlc.spec_toolkit.expressions import ExpressionError, parse_expression
from adlc.spec_toolkit.findings import Finding
from adlc.spec_toolkit.loader import LoadedFile
from adlc.spec_toolkit.rules import REGISTRY, Context

TIERS = ("low", "medium", "high")
NON_TERMINATING = ("pass", "rework", "exception", "escalate")

# Constitution III: who may set which outcome. Platform rule, identical for every terminal.
ALLOWED_STATUS_RIGHTS: dict[str, frozenset[str]] = {
    "human": frozenset({"pass", "rework", "exception", "terminate"}),
    "reviewer": frozenset({"recommend"}),
    "orchestrator": frozenset({"escalate", "rework_on_auto_rollback"}),
    "agent": frozenset({"raise_event"}),
}
AGENT_FORBIDDEN = frozenset({"pass", "exception", "terminate"})


def spec(loaded: LoadedFile) -> dict[str, Any]:
    data = loaded.data.get("terminal") if isinstance(loaded.data, dict) else None
    return data if isinstance(data, dict) else {}


def _get(node: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _list(node: Any) -> list[Any]:
    return node if isinstance(node, list) else []


def sign_off_rules(t: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """(pointer, rule) for plain, by_tier and by_mode sign-off forms."""
    base = "/terminal/authorities/sign_off"
    sign_off = _get(t, "authorities", "sign_off")
    if not isinstance(sign_off, dict):
        return
    for group in ("by_tier", "by_mode"):
        if isinstance(sign_off.get(group), dict):
            for key, rule in sign_off[group].items():
                if isinstance(rule, dict):
                    yield f"{base}/{group}/{key}", rule
            return
    yield base, sign_off


def expressions(t: dict[str, Any]) -> Iterator[tuple[str, str]]:
    """(pointer, expression) for every CEL expression in a terminal spec."""
    for i, p in enumerate(_list(t.get("prerequisites"))):
        if isinstance(p, dict) and isinstance(p.get("condition"), str):
            yield f"/terminal/prerequisites/{i}/condition", p["condition"]
    for i, c in enumerate(_list(_get(t, "controls", "automated"))):
        if isinstance(c, dict) and isinstance(c.get("rule"), str):
            yield f"/terminal/controls/automated/{i}/rule", c["rule"]
    for i, p in enumerate(_list(_get(t, "playbooks", "procedures"))):
        if isinstance(p, dict) and isinstance(p.get("applies_when"), str):
            yield f"/terminal/playbooks/procedures/{i}/applies_when", p["applies_when"]
    for i, m in enumerate(_list(t.get("monitors"))):
        if isinstance(m, dict) and isinstance(m.get("threshold"), str):
            yield f"/terminal/monitors/{i}/threshold", m["threshold"]
    for i, a in enumerate(_list(_get(t, "evidence", "artifacts"))):
        when = _get(a, "applicability", "when")
        if isinstance(when, str):
            yield f"/terminal/evidence/artifacts/{i}/applicability/when", when
    model = t.get("outcome_model")
    outcomes: dict[str, Any] = model if isinstance(model, dict) else {}
    for status, outcome in outcomes.items():
        if status != "event_routes" and isinstance(_get(outcome, "when"), str):
            yield f"/terminal/outcome_model/{status}/when", outcome["when"]
    event_routes = _get(t, "outcome_model", "event_routes")
    for event, route in (event_routes if isinstance(event_routes, dict) else {}).items():
        if isinstance(_get(route, "then_when"), str):
            yield f"/terminal/outcome_model/event_routes/{event}/then_when", route["then_when"]
    if isinstance(_get(t, "authorities", "emergency", "when"), str):
        yield "/terminal/authorities/emergency/when", t["authorities"]["emergency"]["when"]
    for base, rule in sign_off_rules(t):
        for i, plus in enumerate(_list(rule.get("plus"))):
            if isinstance(_get(plus, "when"), str):
                yield f"{base}/plus/{i}/when", plus["when"]
        if isinstance(_get(rule, "external", "when"), str):
            yield f"{base}/external/when", rule["external"]["when"]


def evidence_refs(t: dict[str, Any]) -> Iterator[tuple[str, str]]:
    """(pointer, dotted reference) for evidence_ref fields (not expressions)."""
    for i, p in enumerate(_list(t.get("prerequisites"))):
        if isinstance(p, dict) and isinstance(p.get("evidence_ref"), str):
            yield f"/terminal/prerequisites/{i}/evidence_ref", p["evidence_ref"]
    bound = _get(t, "evidence", "ledger", "bound_to")
    if isinstance(bound, str):
        yield "/terminal/evidence/ledger/bound_to", bound


def terminal_number(loaded: LoadedFile) -> str | None:
    match = re.match(r"^terminals/T([0-9]+)\.yaml$", loaded.rel)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------- V-01 (local)


def local_duplicate_ids(ctx: Context, loaded: LoadedFile) -> Iterator[Finding]:
    t = spec(loaded)
    groups = [
        ("/terminal/prerequisites", _list(t.get("prerequisites")), "id"),
        ("/terminal/controls/automated", _list(_get(t, "controls", "automated")), "id"),
        ("/terminal/playbooks/procedures", _list(_get(t, "playbooks", "procedures")), "id"),
        ("/terminal/monitors", _list(t.get("monitors")), "id"),
        ("/terminal/evidence/artifacts", _list(_get(t, "evidence", "artifacts")), "id"),
    ]
    for base, items, key in groups:
        seen: set[str] = set()
        for i, item in enumerate(items):
            value = str(_get(item, key))
            if value in seen:
                yield ctx.finding("V-01", loaded.rel, f"{base}/{i}", f"{value} defined twice")
            seen.add(value)
    items = _list(_get(t, "controls", "checklist", "items"))
    for value, count in Counter(str(v) for v in items).items():
        if count > 1:
            yield ctx.finding(
                "V-01", loaded.rel, "/terminal/controls/checklist/items", f"{value} listed twice"
            )


# ---------------------------------------------------------------------------- L3 rules


@REGISTRY.rule("V-04", "L3", "error", "Every non-terminating outcome has a route")
def v04_routes(ctx: Context) -> Iterator[Finding]:
    for loaded in ctx.terminals():
        outcomes = _get(spec(loaded), "outcome_model") or {}
        for status in NON_TERMINATING:
            outcome = outcomes.get(status) or {}
            if not (
                outcome.get("route")
                or outcome.get("route_by_root_cause")
                or outcome.get("not_allowed")
            ):
                yield ctx.finding(
                    "V-04",
                    loaded.rel,
                    f"/terminal/outcome_model/{status}",
                    f"{status} has no route, route_by_root_cause or not_allowed",
                )


@REGISTRY.rule("V-07", "L3", "error", "No permission in both allow and deny")
def v07_allow_deny(ctx: Context) -> Iterator[Finding]:
    for loaded in ctx.terminals():
        auth = _get(spec(loaded), "authorities") or {}
        for permission in sorted(set(_list(auth.get("allow"))) & set(_list(auth.get("deny")))):
            yield ctx.finding(
                "V-07", loaded.rel, "/terminal/authorities", f"{permission} in both allow and deny"
            )


def _tiered(t: dict[str, Any]) -> Iterator[tuple[str, Any]]:
    yield "/terminal/timeline/expected_duration", _get(t, "timeline", "expected_duration")
    yield "/terminal/timeline/retirement_duration", _get(t, "timeline", "retirement_duration")
    yield "/terminal/trigger/review_schedule", _get(t, "trigger", "review_schedule")
    yield "/terminal/controls/tiering", _get(t, "controls", "tiering")
    yield "/terminal/authorities/sign_off/by_tier", _get(t, "authorities", "sign_off", "by_tier")


@REGISTRY.rule("V-08", "L3", "error", "Every tiered value defines low, medium and high")
def v08_tiers(ctx: Context) -> Iterator[Finding]:
    for loaded in ctx.terminals():
        for pointer, value in _tiered(spec(loaded)):
            if isinstance(value, dict):
                missing = [t for t in TIERS if t not in value]
                if missing:
                    yield ctx.finding(
                        "V-08", loaded.rel, pointer, f"tiered value missing {', '.join(missing)}"
                    )


@REGISTRY.rule("V-09", "L3", "error", "Agents never hold pass, exception or terminate")
def v09_agent_rights(ctx: Context) -> Iterator[Finding]:
    for loaded in ctx.terminals():
        agent = _list(_get(spec(loaded), "authorities", "status_rights", "agent"))
        for right in sorted(set(agent) & AGENT_FORBIDDEN):
            yield ctx.finding(
                "V-09",
                loaded.rel,
                "/terminal/authorities/status_rights/agent",
                f"agent may not hold {right}",
            )


@REGISTRY.rule("V-11", "L3", "error", "Every expression parses as CEL")
def v11_expressions_parse(ctx: Context) -> Iterator[Finding]:
    for loaded in ctx.terminals():
        for pointer, text in expressions(spec(loaded)):
            try:
                parse_expression(text)
            except ExpressionError as exc:
                where = f" (column {exc.column})" if exc.column else ""
                yield ctx.finding(
                    "V-11", loaded.rel, pointer, f"cannot parse {text!r}: {exc}{where}"
                )


@REGISTRY.rule("V-14", "L3", "error", "Every artifact has valid applicability")
def v14_applicability(ctx: Context) -> Iterator[Finding]:
    for loaded in ctx.terminals():
        for i, artifact in enumerate(_list(_get(spec(loaded), "evidence", "artifacts"))):
            app = _get(artifact, "applicability") or {}
            mode, when = app.get("mode"), app.get("when")
            pointer = f"/terminal/evidence/artifacts/{i}/applicability"
            if mode == "conditional" and not when:
                yield ctx.finding(
                    "V-14", loaded.rel, pointer, "conditional applicability needs 'when'"
                )
            if mode in ("mandatory", "optional") and when:
                yield ctx.finding(
                    "V-14", loaded.rel, pointer, f"{mode} applicability takes no 'when'"
                )


@REGISTRY.rule("V-15", "L3", "error", "Status rights follow constitution III")
def v15_status_rights(ctx: Context) -> Iterator[Finding]:
    for loaded in ctx.terminals():
        rights = _get(spec(loaded), "authorities", "status_rights") or {}
        for actor, values in rights.items():
            allowed = ALLOWED_STATUS_RIGHTS.get(actor, frozenset())
            for right in _list(values):
                if right not in allowed:
                    yield ctx.finding(
                        "V-15",
                        loaded.rel,
                        f"/terminal/authorities/status_rights/{actor}",
                        f"{actor} may not hold {right} (constitution III)",
                    )


@REGISTRY.rule("V-20", "L3", "error", "File name matches metadata.id")
def v20_file_name(ctx: Context) -> Iterator[Finding]:
    for loaded in ctx.terminals():
        number = terminal_number(loaded)
        declared = _get(spec(loaded), "metadata", "id")
        if number is not None and declared != f"T{number}":
            yield ctx.finding(
                "V-20",
                loaded.rel,
                "/terminal/metadata/id",
                f"{loaded.rel} declares metadata.id {declared}",
            )


@REGISTRY.rule("V-21", "L3", "error", "Exactly one A per scope in human_roles")
def v21_one_accountable(ctx: Context) -> Iterator[Finding]:
    for loaded in ctx.terminals():
        roles = _list(_get(spec(loaded), "actors", "human_roles"))
        per_scope = Counter(
            str(r.get("scope") or "whole terminal")
            for r in roles
            if isinstance(r, dict) and r.get("raci") == "A"
        )
        for scope, count in per_scope.items():
            if count > 1:
                yield ctx.finding(
                    "V-21",
                    loaded.rel,
                    "/terminal/actors/human_roles",
                    f"{count} roles hold A for {scope}",
                )
        if not per_scope:
            yield ctx.finding("V-21", loaded.rel, "/terminal/actors/human_roles", "no role holds A")
