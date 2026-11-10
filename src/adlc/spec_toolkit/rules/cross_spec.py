"""L4 rules: references across files and catalogues (contracts/validation-rules.md).

Rules iterate over whatever specs and catalogues declare; no terminal, role or event name is
written in this module (constitution I).
"""

import fnmatch
import re
from collections.abc import Iterator
from typing import Any

from adlc.spec_toolkit.catalogues import Catalogues
from adlc.spec_toolkit.expressions import Arg, ExpressionError, ParsedExpression, parse_expression
from adlc.spec_toolkit.findings import Finding
from adlc.spec_toolkit.graph import (
    END,
    TERMINAL_ID,
    LifecycleGraph,
    build_graph,
    classify,
    event_route_destinations,
    outcome_destinations,
    terminal_id,
)
from adlc.spec_toolkit.loader import LoadedFile
from adlc.spec_toolkit.rules import REGISTRY, Context
from adlc.spec_toolkit.rules.single_spec import (
    evidence_refs,
    expressions,
    local_duplicate_ids,
    sign_off_rules,
    spec,
    terminal_number,
)

# Annex A.4 metric suffix per unit; units without an entry have no suffix rule.
_METRIC_SUFFIX = {"ratio": "_rate", "pct": "_pct", "ms": "_ms", "usd": "_usd", "count": "_count"}
_GUARDRAIL_NAME = re.compile(r"^[a-z][a-z0-9_]*_(min|max)$")
_TIERS = ("low", "medium", "high")

# Catalogue list keys and the field that identifies an entry (V-01 uniqueness).
_CATALOGUE_KEYS: dict[str, list[tuple[str, str]]] = {
    "roles": [("roles", "id")],
    "risk_tiers": [("risk_tiers", "id")],
    "events": [("external", "id"), ("operational", "id"), ("patterns", "pattern")],
    "root_causes": [("root_causes", "id")],
    "change_classes": [("change_classes", "id")],
    "data_classes": [("data_classes", "id"), ("resolvers", "id")],
    "model_tiers": [("model_tiers", "id")],
    "mcp_servers": [("mcp_servers", "id")],
    "evidence_sources": [("evidence_sources", "id")],
    "route_destinations": [("route_destinations", "id")],
    "predicates": [("predicates", "name")],
    "metrics": [("metrics", "name")],
    "guardrails": [("guardrails", "name")],
    "agents": [("agents", "id")],
}


def catalogues(ctx: Context) -> Catalogues:
    result: Catalogues = ctx.memo("catalogues", lambda: Catalogues.from_bundle(ctx.bundle))
    return result


def _entries(ctx: Context, name: str, key: str) -> list[tuple[int, dict[str, Any]]]:
    value = ctx.catalogue(name).get(key)
    if not isinstance(value, list):
        return []
    return [(i, v) for i, v in enumerate(value) if isinstance(v, dict)]


def _catalogue_rel(ctx: Context, name: str) -> str:
    loaded = ctx.bundle.catalogues.get(name)
    return loaded.rel if loaded else f"shared/{name}.yaml"


def _usable_catalogue(ctx: Context, name: str) -> bool:
    loaded = ctx.bundle.catalogues.get(name)
    return loaded is not None and not loaded.parse_failed and not loaded.schema_failed


# ---------------------------------------------------------------------------- V-01


def catalogue_duplicates(ctx: Context) -> Iterator[Finding]:
    for name, keys in _CATALOGUE_KEYS.items():
        if not _usable_catalogue(ctx, name):
            continue
        rel = _catalogue_rel(ctx, name)
        for list_key, id_field in keys:
            seen: set[str] = set()
            for i, entry in _entries(ctx, name, list_key):
                value = str(entry.get(id_field))
                if value in seen:
                    yield ctx.finding(
                        "V-01", rel, f"/{list_key}/{i}", f"{id_field} {value} defined twice"
                    )
                seen.add(value)


# ---------------------------------------------------------------------------- V-18


def catalogue_naming(ctx: Context) -> Iterator[Finding]:
    if _usable_catalogue(ctx, "guardrails"):
        rel = _catalogue_rel(ctx, "guardrails")
        for i, entry in _entries(ctx, "guardrails", "guardrails"):
            name = str(entry.get("name"))
            if not _GUARDRAIL_NAME.match(name):
                yield ctx.finding(
                    "V-18",
                    rel,
                    f"/guardrails/{i}/name",
                    f"guardrail {name}: expected <measure>_<min|max> (SA Annex A.4)",
                )
    if _usable_catalogue(ctx, "metrics"):
        rel = _catalogue_rel(ctx, "metrics")
        for i, entry in _entries(ctx, "metrics", "metrics"):
            name, unit = str(entry.get("name")), str(entry.get("unit"))
            suffix = _METRIC_SUFFIX.get(unit)
            if suffix and not name.endswith(suffix):
                yield ctx.finding(
                    "V-18",
                    rel,
                    f"/metrics/{i}/name",
                    f"metric {name} has unit {unit}: name must end with {suffix} (SA Annex A.4)",
                )


# ---------------------------------------------------------------------------- V-19


@REGISTRY.rule("V-19", "L4", "error", "Tighten-only guardrails are monotonic across risk tiers")
def v19_guardrail_monotonic(ctx: Context) -> Iterator[Finding]:
    if not _usable_catalogue(ctx, "guardrails"):
        return
    rel = _catalogue_rel(ctx, "guardrails")
    for i, entry in _entries(ctx, "guardrails", "guardrails"):
        if not entry.get("tighten_only") or entry.get("monotonic") is False:
            continue
        values = entry.get("values") or {}
        if not all(t in values for t in _TIERS):
            continue  # V-08 reports incomplete tiers
        low, medium, high = (values[t] for t in _TIERS)
        direction, name = entry.get("direction"), entry.get("name")
        ok = True
        if direction == "max":
            ok = high <= medium <= low
        elif direction == "min":
            ok = high >= medium >= low
        elif direction == "superset":
            ok = set(low) <= set(medium) <= set(high)
        if not ok:
            yield ctx.finding(
                "V-19",
                rel,
                f"/guardrails/{i}/values",
                f"guardrail {name} ({direction}) loosens as risk rises: "
                f"low={low}, medium={medium}, high={high}",
            )


# Run variables the orchestrator provides to every expression (TDS B.3, namespaced as run.*).
RUN_VARIABLES = frozenset(
    {"rework_count", "age", "now", "usecase_id", "run_version", "risk_tier", "mode"}
)
# CEL functions and methods that need no catalogue entry.
CEL_FUNCTIONS = frozenset(
    {
        "size",
        "has",
        "int",
        "uint",
        "double",
        "string",
        "bool",
        "bytes",
        "duration",
        "timestamp",
        "type",
        "matches",
    }
)
CEL_METHODS = frozenset(
    {
        "all",
        "exists",
        "exists_one",
        "map",
        "filter",
        "size",
        "contains",
        "startsWith",
        "endsWith",
        "matches",
    }
)
DURATION = re.compile(r"^[0-9]+(h|d|w|m)$")


def graph(ctx: Context) -> LifecycleGraph:
    result: LifecycleGraph = ctx.memo(
        "graph", lambda: build_graph(ctx.terminals(), catalogues(ctx))
    )
    return result


def _parsed(text: str) -> ParsedExpression | None:
    try:
        return parse_expression(text)
    except ExpressionError:
        return None  # V-11 reports it


def _known_terminals(ctx: Context) -> set[str]:
    return set(graph(ctx).terminals)


def _artifacts(loaded: LoadedFile) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for artifact in spec(loaded).get("evidence", {}).get("artifacts") or []:
        if isinstance(artifact, dict) and isinstance(artifact.get("id"), str):
            result[artifact["id"]] = [str(c) for c in artifact.get("columns") or []]
    return result


def _emitted_values(loaded: LoadedFile) -> set[str]:
    values: set[str] = set()
    for outcome in (spec(loaded).get("outcome_model") or {}).values():
        if isinstance(outcome, dict):
            for item in outcome.get("emits") or []:
                values.add(str(item).split(".")[0])
    return values


def _all_refs(t: dict[str, Any]) -> Iterator[tuple[str, tuple[str, ...]]]:
    """(pointer, path) for every reference in evidence_ref fields and expressions."""
    for pointer, dotted in evidence_refs(t):
        yield pointer, tuple(dotted.split("."))
    for pointer, text in expressions(t):
        parsed = _parsed(text)
        if parsed is not None:
            for ref in parsed.refs:
                yield pointer, ref.path
    for pointer, _, dest in [*outcome_destinations(t), *event_route_destinations(t)]:
        for template in re.findall(r"\$\{([^}]+)\}", dest):
            yield pointer, tuple(template.split("."))
    window = (t.get("trigger") or {}).get("window")
    if isinstance(window, str):
        for template in re.findall(r"\$\{([^}]+)\}", window):
            yield "/terminal/trigger/window", tuple(template.split("."))


# ---------------------------------------------------------------------------- V-01


@REGISTRY.rule("V-01", "L4", "error", "Ids unique within a spec, terminal ids unique across files")
def v01_unique_ids(ctx: Context) -> Iterator[Finding]:
    yield from catalogue_duplicates(ctx)
    owners: dict[str, str] = {}
    for loaded in ctx.terminals():
        yield from local_duplicate_ids(ctx, loaded)
        tid = terminal_id(loaded)
        if tid is None:
            continue
        if tid in owners:
            yield ctx.finding(
                "V-01",
                loaded.rel,
                "/terminal/metadata/id",
                f"terminal id {tid} also defined in {owners[tid]}",
            )
        else:
            owners[tid] = loaded.rel


# ---------------------------------------------------------------------------- V-02


@REGISTRY.rule(
    "V-02", "L4", "error", "Evidence references resolve and come from a reachable terminal"
)
def v02_evidence_refs(ctx: Context) -> Iterator[Finding]:
    lg = graph(ctx)
    record_fields = catalogues(ctx).terminal_record_fields
    for loaded in ctx.terminals():
        me = terminal_id(loaded)
        for pointer, path in _all_refs(spec(loaded)):
            root = path[0]
            if not TERMINAL_ID.match(root):
                continue
            dotted = ".".join(path)
            target = lg.terminals.get(root)
            if target is None:
                yield ctx.finding("V-02", loaded.rel, pointer, f"{dotted}: unknown terminal {root}")
                continue
            if len(path) == 1:
                continue
            name = path[1]
            artifacts = _artifacts(target)
            if name in artifacts:
                if len(path) > 2 and path[2] not in artifacts[name]:
                    yield ctx.finding(
                        "V-02",
                        loaded.rel,
                        pointer,
                        f"{dotted}: artifact {root}.{name} has no column {path[2]}",
                    )
                    continue
            elif name not in _emitted_values(target) and name not in record_fields:
                yield ctx.finding(
                    "V-02",
                    loaded.rel,
                    pointer,
                    f"{dotted}: {root} has no artifact, emitted value or record field {name}",
                )
                continue
            if me is not None and not lg.reaches(root, me):
                yield ctx.finding(
                    "V-02",
                    loaded.rel,
                    pointer,
                    f"{dotted}: {root} cannot reach {me} in the route graph",
                )


# ---------------------------------------------------------------------------- V-03


@REGISTRY.rule("V-03", "L4", "error", "Every trigger event is produced or external")
def v03_trigger_events(ctx: Context) -> Iterator[Finding]:
    lg = graph(ctx)
    produced = lg.producers()
    external = catalogues(ctx).external_events
    for loaded in ctx.terminals():
        for i, event in enumerate((spec(loaded).get("trigger") or {}).get("on") or []):
            if event not in produced and event not in external:
                yield ctx.finding(
                    "V-03",
                    loaded.rel,
                    f"/terminal/trigger/on/{i}",
                    f"trigger event {event} is not produced by any terminal nor external",
                )


# ---------------------------------------------------------------------------- V-05


def _role_uses(t: dict[str, Any]) -> Iterator[tuple[str, str]]:
    meta = t.get("metadata") or {}
    if isinstance(meta.get("owner_role"), str):
        yield "/terminal/metadata/owner_role", meta["owner_role"]
    for i, role in enumerate((t.get("actors") or {}).get("human_roles") or []):
        if isinstance(role, dict):
            yield f"/terminal/actors/human_roles/{i}", str(role.get("role"))
    for base, rule in sign_off_rules(t):
        for role in rule.get("roles") or []:
            yield f"{base}/roles", str(role)
        for i, plus in enumerate(rule.get("plus") or []):
            yield f"{base}/plus/{i}", str((plus or {}).get("role"))
        for stage, role in (rule.get("stage_approval") or {}).items():
            yield f"{base}/stage_approval/{stage}", str(role)
    for status, outcome in (t.get("outcome_model") or {}).items():
        if isinstance(outcome, dict) and status != "event_routes":
            for key in ("set_by", "notify"):
                for role in outcome.get(key) or []:
                    yield f"/terminal/outcome_model/{status}/{key}", str(role)
    for event, route in ((t.get("outcome_model") or {}).get("event_routes") or {}).items():
        for role in (route or {}).get("notify") or []:
            yield f"/terminal/outcome_model/event_routes/{event}/notify", str(role)
    auth = t.get("authorities") or {}
    for role in (auth.get("emergency") or {}).get("notify") or []:
        yield "/terminal/authorities/emergency/notify", str(role)
    retirement = auth.get("retirement") or {}
    if isinstance(retirement.get("requires"), str):
        yield "/terminal/authorities/retirement/requires", retirement["requires"]


@REGISTRY.rule("V-05", "L4", "error", "Roles exist; sign-off roles hold A or R")
def v05_roles(ctx: Context) -> Iterator[Finding]:
    roles = catalogues(ctx).role_ids
    for loaded in ctx.terminals():
        t = spec(loaded)
        for pointer, role in _role_uses(t):
            if role not in roles:
                yield ctx.finding("V-05", loaded.rel, pointer, f"role {role} not in roles.yaml")
        accountable = {
            str(r.get("role"))
            for r in (t.get("actors") or {}).get("human_roles") or []
            if isinstance(r, dict) and r.get("raci") in ("A", "R")
        }
        for base, rule in sign_off_rules(t):
            for role in rule.get("roles") or []:
                if role not in accountable:
                    yield ctx.finding(
                        "V-05",
                        loaded.rel,
                        f"{base}/roles",
                        f"sign-off role {role} must hold A or R in human_roles",
                    )


# ---------------------------------------------------------------------------- V-06


@REGISTRY.rule("V-06", "L4", "error", "Tool scopes and grounding servers exist in the MCP registry")
def v06_mcp(ctx: Context) -> Iterator[Finding]:
    servers = catalogues(ctx).mcp_scopes
    for loaded in ctx.terminals():
        t = spec(loaded)
        for i, scope in enumerate((t.get("authorities") or {}).get("tool_scopes") or []):
            parts = str(scope).split(":")
            if len(parts) != 3 or parts[1] not in servers or parts[2] not in servers[parts[1]]:
                yield ctx.finding(
                    "V-06",
                    loaded.rel,
                    f"/terminal/authorities/tool_scopes/{i}",
                    f"tool scope {scope} is not in the MCP registry (shared/mcp_servers.yaml)",
                )
        for i, ground in enumerate((t.get("playbooks") or {}).get("grounding") or []):
            server = (ground or {}).get("mcp")
            if server not in servers:
                yield ctx.finding(
                    "V-06",
                    loaded.rel,
                    f"/terminal/playbooks/grounding/{i}",
                    f"grounding server {server} is not in the MCP registry",
                )


# ---------------------------------------------------------------------------- V-10


@REGISTRY.rule("V-10", "L4", "error", "Playbook and checklist refs exist at the stated version")
def v10_refs(ctx: Context) -> Iterator[Finding]:
    playbooks = {p.rel: p.data for p in ctx.bundle.playbooks.values() if isinstance(p.data, dict)}
    checklists = {c.rel: c.data for c in ctx.bundle.checklists.values() if isinstance(c.data, dict)}
    for loaded in ctx.terminals():
        t = spec(loaded)
        for i, proc in enumerate((t.get("playbooks") or {}).get("procedures") or []):
            proc = proc or {}
            found = playbooks.get(str(proc.get("ref")))
            if (
                found is None
                or found.get("id") != proc.get("id")
                or found.get("version") != proc.get("version")
            ):
                yield ctx.finding(
                    "V-10",
                    loaded.rel,
                    f"/terminal/playbooks/procedures/{i}",
                    f"playbook {proc.get('id')} {proc.get('version')} "
                    f"not found at {proc.get('ref')}",
                )
        checklist = (t.get("controls") or {}).get("checklist") or {}
        found_list = checklists.get(str(checklist.get("ref")))
        pointer = "/terminal/controls/checklist"
        if found_list is None or found_list.get("version") != checklist.get("version"):
            yield ctx.finding(
                "V-10",
                loaded.rel,
                pointer,
                f"checklist {checklist.get('ref')} {checklist.get('version')} not found",
            )
            continue
        known_items = {str((i or {}).get("id")) for i in found_list.get("items") or []}
        for item in checklist.get("items") or []:
            if item not in known_items:
                yield ctx.finding(
                    "V-10",
                    loaded.rel,
                    pointer,
                    f"checklist item {item} not in {checklist.get('ref')}",
                )


# ---------------------------------------------------------------------------- V-12, V-13


def _check_ref(path: tuple[str, ...], t: dict[str, Any], cats: Catalogues) -> str | None:
    """Return a problem message for a non-terminal reference, or None if it resolves."""
    root = path[0]
    rest = path[1] if len(path) > 1 else None
    if TERMINAL_ID.match(root):
        return None  # V-02
    if root == "param":
        return None if rest in cats.guardrails else f"param.{rest}: no such guardrail"
    if root == "tier":
        keys = {
            k
            for tier in ((t.get("controls") or {}).get("tiering") or {}).values()
            if isinstance(tier, dict)
            for k in tier
        }
        return None if rest in keys else f"tier.{rest}: no such key in controls.tiering"
    if root == "timeline":
        return None if rest in (t.get("timeline") or {}) else f"timeline.{rest}: not in timeline"
    if root == "run":
        return None if rest in RUN_VARIABLES else f"run.{rest}: unknown run variable"
    if root in cats.evidence_sources and root != "terminal_record":
        fields = cats.evidence_sources[root]
        if rest is None or not fields or rest in fields:
            return None
        return f"{root}.{rest}: {root} has no field {rest}"
    return f"{'.'.join(path)}: unknown name {root}"


def _check_arg(arg: Arg, kind: str, cats: Catalogues) -> str | None:
    if kind == "any":
        return None
    if kind == "evidence_ref":
        return None if arg.kind == "ref" else "expected an evidence reference"
    if kind in ("terminal_list", "string_list"):
        if arg.kind != "list":
            return "expected a list literal"
        if kind == "terminal_list" and not all(TERMINAL_ID.match(i) for i in arg.items):
            return "expected a list of terminal ids"
        return None
    if kind in ("string", "duration", "role"):
        if arg.kind != "string":
            return f"expected a {kind} string literal"
        if kind == "duration" and not DURATION.match(arg.text):
            return f"{arg.text!r} is not a duration"
        if kind == "role" and arg.text not in cats.role_ids:
            return f"role {arg.text} not in roles.yaml"
        return None
    if kind == "number":
        return None if arg.kind in ("number", "ref", "other") else "expected a number"
    return None


@REGISTRY.rule(
    "V-12", "L4", "error", "Every name in expressions and routing resolves to a catalogue"
)
def v12_names(ctx: Context) -> Iterator[Finding]:
    cats = catalogues(ctx)
    known = _known_terminals(ctx)
    for loaded in ctx.terminals():
        t = spec(loaded)
        rel = loaded.rel
        for pointer, path in _all_refs(t):
            problem = _check_ref(path, t, cats)
            if problem:
                yield ctx.finding("V-12", rel, pointer, problem)
        for pointer, text in expressions(t):
            parsed = _parsed(text)
            if parsed is None:
                continue
            for call in parsed.calls:
                if call.name not in cats.predicates and call.name not in CEL_FUNCTIONS:
                    yield ctx.finding("V-12", rel, pointer, f"unknown predicate {call.name}")
            for method in parsed.methods:
                if method not in CEL_METHODS:
                    yield ctx.finding("V-12", rel, pointer, f"unknown method {method}")
        outcomes = t.get("outcome_model") or {}
        for cause in (outcomes.get("rework") or {}).get("route_by_root_cause") or {}:
            if cause not in cats.root_causes:
                yield ctx.finding(
                    "V-12",
                    rel,
                    "/terminal/outcome_model/rework/route_by_root_cause",
                    f"root cause {cause} not in root_causes.yaml",
                )
        for name in t.get("change_classes") or {}:
            if name not in cats.change_classes:
                yield ctx.finding(
                    "V-12", rel, f"/terminal/change_classes/{name}", f"change class {name} unknown"
                )
        max_class = ((t.get("authorities") or {}).get("data_access") or {}).get("max_class")
        if max_class not in cats.data_classes and max_class not in cats.data_class_resolvers:
            yield ctx.finding(
                "V-12",
                rel,
                "/terminal/authorities/data_access/max_class",
                f"data class {max_class} unknown",
            )
        tier = ((t.get("actors") or {}).get("agent") or {}).get("model_tier")
        if tier not in cats.model_tiers:
            yield ctx.finding(
                "V-12", rel, "/terminal/actors/agent/model_tier", f"model tier {tier} unknown"
            )
        auth = t.get("authorities") or {}
        perms = [
            *(auth.get("allow") or []),
            *(auth.get("deny") or []),
            *((auth.get("emergency") or {}).get("allow") or []),
            *((auth.get("retirement") or {}).get("allow") or []),
        ]
        for permission in perms:
            verb = str(permission).split(":")[0]
            if verb not in cats.permission_verbs:
                yield ctx.finding(
                    "V-12", rel, "/terminal/authorities", f"permission verb {verb} unknown"
                )
        for pointer, _, dest in [*outcome_destinations(t), *event_route_destinations(t)]:
            if classify(dest, cats, known).kind == "unknown":
                yield ctx.finding("V-12", rel, pointer, f"route destination {dest} unknown")
        raised = {m.get("raises") for m in t.get("monitors") or [] if isinstance(m, dict)}
        for event in outcomes.get("event_routes") or {}:
            if event not in raised:
                yield ctx.finding(
                    "V-12",
                    rel,
                    f"/terminal/outcome_model/event_routes/{event}",
                    f"event route {event} is not raised by any monitor of this terminal",
                )
            name = event.rsplit(".", 1)[-1]
            if name not in cats.operational_events:
                yield ctx.finding(
                    "V-12",
                    rel,
                    f"/terminal/outcome_model/event_routes/{event}",
                    f"operational event {name} not in events.yaml",
                )


@REGISTRY.rule("V-13", "L4", "error", "Predicate calls match their catalogue signature")
def v13_signatures(ctx: Context) -> Iterator[Finding]:
    cats = catalogues(ctx)
    for loaded in ctx.terminals():
        for pointer, text in expressions(spec(loaded)):
            parsed = _parsed(text)
            if parsed is None:
                continue
            for call in parsed.calls:
                predicate = cats.predicates.get(call.name)
                if predicate is None:
                    continue
                if len(call.args) != len(predicate.params):
                    yield ctx.finding(
                        "V-13",
                        loaded.rel,
                        pointer,
                        f"{call.name} expects {len(predicate.params)} arguments, "
                        f"got {len(call.args)}",
                    )
                    continue
                for arg, param in zip(call.args, predicate.params, strict=True):
                    problem = _check_arg(arg, param.kind, cats)
                    if problem:
                        yield ctx.finding(
                            "V-13", loaded.rel, pointer, f"{call.name}({param.name}): {problem}"
                        )


# ---------------------------------------------------------------------------- V-16, V-17


@REGISTRY.rule("V-16", "L4", "error", "Allowed permissions stay within one duty group")
def v16_separation_of_duties(ctx: Context) -> Iterator[Finding]:
    groups = catalogues(ctx).duty_groups
    for loaded in ctx.terminals():
        allow = [str(p) for p in (spec(loaded).get("authorities") or {}).get("allow") or []]
        hit = sorted(
            {
                g
                for g, patterns in groups.items()
                for p in allow
                for pat in patterns
                if fnmatch.fnmatch(p, pat)
            }
        )
        if len(hit) > 1:
            yield ctx.finding(
                "V-16",
                loaded.rel,
                "/terminal/authorities/allow",
                f"allowed permissions span duty groups {', '.join(hit)} (separation of duties)",
            )


@REGISTRY.rule(
    "V-17", "L4", "error", "Routes to a terminal match an event that terminal subscribes to"
)
def v17_route_subscriptions(ctx: Context) -> Iterator[Finding]:
    lg = graph(ctx)
    for loaded in ctx.terminals():
        me = terminal_id(loaded)
        outcomes = spec(loaded).get("outcome_model") or {}
        checks: list[tuple[str, str, str]] = []
        for status in ("pass", "exception"):
            dest = (outcomes.get(status) or {}).get("route")
            if isinstance(dest, str):
                checks.append((f"/terminal/outcome_model/{status}/route", dest, f"{me}.{status}"))
        rework = outcomes.get("rework") or {}
        for cause, dest in (rework.get("route_by_root_cause") or {}).items():
            if isinstance(dest, str):
                checks.append(
                    (
                        f"/terminal/outcome_model/rework/route_by_root_cause/{cause}",
                        dest,
                        f"{me}.rework.{cause}",
                    )
                )
        for pointer, dest, event in checks:
            if dest == me or dest not in lg.terminals:
                continue
            if event not in lg.subscriptions.get(dest, []):
                yield ctx.finding(
                    "V-17",
                    loaded.rel,
                    pointer,
                    f"routes to {dest}, but {dest} does not subscribe to {event}",
                )


# ---------------------------------------------------------------------------- V-18


def spec_naming(ctx: Context, loaded: LoadedFile) -> Iterator[Finding]:
    number = terminal_number(loaded)
    if number is None:
        return
    t = spec(loaded)
    own = f"T{number}"
    groups = [
        ("/terminal/prerequisites", t.get("prerequisites") or [], "PRE-"),
        ("/terminal/controls/automated", (t.get("controls") or {}).get("automated") or [], "CTL-"),
    ]
    for base, items, prefix in groups:
        for i, item in enumerate(items):
            value = str((item or {}).get("id"))
            if not value.startswith(f"{prefix}{own}-"):
                yield ctx.finding(
                    "V-18", loaded.rel, f"{base}/{i}/id", f"{value} should be {prefix}{own}-<nn>"
                )
    for i, proc in enumerate((t.get("playbooks") or {}).get("procedures") or []):
        value = str((proc or {}).get("id"))
        if not (value.startswith(f"PB-{own}-") or value.startswith("PB-SH-")):
            yield ctx.finding(
                "V-18",
                loaded.rel,
                f"/terminal/playbooks/procedures/{i}/id",
                f"{value} should be PB-{own}-<nn> or PB-SH-<nn>",
            )
    checklist = (t.get("controls") or {}).get("checklist") or {}
    for item in checklist.get("items") or []:
        if not str(item).startswith(f"CHK-{own}-"):
            yield ctx.finding(
                "V-18",
                loaded.rel,
                "/terminal/controls/checklist/items",
                f"{item} should be CHK-{own}-<nn>",
            )
    if checklist.get("ref") not in (None, f"checklists/t{number}.yaml"):
        yield ctx.finding(
            "V-18",
            loaded.rel,
            "/terminal/controls/checklist/ref",
            f"checklist ref should be checklists/t{number}.yaml",
        )
    agent = str(((t.get("actors") or {}).get("agent") or {}).get("id"))
    if not agent.startswith(f"t{number}-"):
        yield ctx.finding(
            "V-18",
            loaded.rel,
            "/terminal/actors/agent/id",
            f"agent id {agent} should start t{number}-",
        )
    key = str(((t.get("evidence") or {}).get("ledger") or {}).get("key"))
    if f"/{own}/" not in key:
        yield ctx.finding(
            "V-18",
            loaded.rel,
            "/terminal/evidence/ledger/key",
            f"ledger key should contain /{own}/",
        )
    for i, monitor in enumerate(t.get("monitors") or []):
        raises = str((monitor or {}).get("raises"))
        if not raises.startswith(f"{own}.event."):
            yield ctx.finding(
                "V-18",
                loaded.rel,
                f"/terminal/monitors/{i}/raises",
                f"monitor event {raises} should be {own}.event.<name>",
            )


@REGISTRY.rule("V-18", "L4", "error", "SA Annex A naming for ids, names and catalogue entries")
def v18_naming(ctx: Context) -> Iterator[Finding]:
    yield from catalogue_naming(ctx)
    for loaded in ctx.terminals():
        yield from spec_naming(ctx, loaded)


# ---------------------------------------------------------------------------- V-22, V-23, V-26


@REGISTRY.rule(
    "V-22", "L4", "error", "Every terminal is reachable from an external event and can end"
)
def v22_reachability(ctx: Context) -> Iterator[Finding]:
    lg = graph(ctx)
    sources = [n for n in lg.graph.nodes if str(n).startswith("ext:")]
    for tid, loaded in lg.terminals.items():
        if not any(lg.reaches(source, tid) for source in sources):
            yield ctx.finding(
                "V-22",
                loaded.rel,
                "/terminal/trigger/on",
                f"{tid} is not reachable from any external event",
            )
        if not lg.reaches(tid, END):
            yield ctx.finding(
                "V-22",
                loaded.rel,
                "/terminal/outcome_model",
                f"{tid} cannot reach a terminating outcome",
            )


@REGISTRY.rule("V-23", "L4", "info", "Catalogue entries not used by any spec")
def v23_unused(ctx: Context) -> Iterator[Finding]:
    cats = catalogues(ctx)
    used_predicates: set[str] = set()
    used_servers: set[str] = set()
    for loaded in ctx.terminals():
        t = spec(loaded)
        for _, text in expressions(t):
            parsed = _parsed(text)
            if parsed is not None:
                used_predicates.update(c.name for c in parsed.calls)
        for scope in (t.get("authorities") or {}).get("tool_scopes") or []:
            parts = str(scope).split(":")
            if len(parts) == 3:
                used_servers.add(parts[1])
        for ground in (t.get("playbooks") or {}).get("grounding") or []:
            used_servers.add(str((ground or {}).get("mcp")))
    for name in sorted(set(cats.predicates) - used_predicates):
        yield ctx.finding(
            "V-23", _catalogue_rel(ctx, "predicates"), "/predicates", f"predicate {name} unused"
        )
    for name in sorted(set(cats.mcp_scopes) - used_servers):
        yield ctx.finding(
            "V-23", _catalogue_rel(ctx, "mcp_servers"), "/mcp_servers", f"MCP server {name} unused"
        )


@REGISTRY.rule("V-26", "L4", "warning", "A guardrail used by a spec is still a proposed default")
def v26_proposed_defaults(ctx: Context) -> Iterator[Finding]:
    guardrails = catalogues(ctx).guardrails
    for loaded in ctx.terminals():
        reported: set[str] = set()
        for pointer, path in _all_refs(spec(loaded)):
            if path[0] == "param" and len(path) > 1:
                guard = guardrails.get(path[1])
                if guard is not None and guard.proposed_default and path[1] not in reported:
                    reported.add(path[1])
                    yield ctx.finding(
                        "V-26",
                        loaded.rel,
                        pointer,
                        f"param.{path[1]} is a proposed default awaiting owner confirmation",
                    )
