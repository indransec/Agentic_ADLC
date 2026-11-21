"""Rules for the tracker mapping (feature 016; contracts/tracker-mapping.md "Rules").

The mapping says how the platform appears on a board. These rules check it against its schema and
against what the platform needs from it: a column for every terminal the specs declare, a state
and a sub-stage for every run state, a decision value for every human outcome any terminal grants
and for the waiver and escalation actions, and distinct field references. No terminal, outcome or
tracker name is written here: terminals and outcomes come from the specs, run states from the
state machine.
"""

from collections.abc import Iterator
from typing import Any

from adlc.orchestration.states import RunState
from adlc.spec_toolkit.findings import Finding
from adlc.spec_toolkit.rules import REGISTRY, Context
from adlc.spec_toolkit.rules.single_spec import spec
from adlc.spec_toolkit.schema import _check

# Platform actions a board decision can request besides the sign-off outcomes (R-06).
# Decisions made only on the board (no terminal outcome names them); 020 adds the change request's
BOARD_ACTIONS = (
    "approve_waiver",
    "reject_waiver",
    "complete_escalation",
    "approve_change",
    "reject_change",
)


def _mapping(ctx: Context) -> tuple[str, dict[str, Any]] | None:
    loaded = ctx.bundle.tracker_mapping
    if loaded is None or loaded.parse_failed or loaded.schema_failed:
        return None
    if not isinstance(loaded.data, dict):
        return None
    return loaded.rel, loaded.data


def _section(data: dict[str, Any], *keys: str) -> Any:
    node: Any = data
    for key in keys:
        node = node.get(key) if isinstance(node, dict) else None
    return node


@REGISTRY.rule("V-32", "L2", "error", "The tracker mapping matches its schema")
def v32_schema(ctx: Context) -> Iterator[Finding]:
    loaded = ctx.bundle.tracker_mapping
    if loaded is None:
        return
    schema = ctx.bundle.root / "schema" / "catalogues" / "tracker_mapping.schema.json"
    for finding in _check(ctx, "S-02", loaded, schema):
        yield ctx.finding("V-32", finding.file, finding.path, finding.message)


@REGISTRY.rule("V-33", "L4", "error", "Every terminal has a distinct column in the tracker mapping")
def v33_columns(ctx: Context) -> Iterator[Finding]:
    found = _mapping(ctx)
    if found is None:
        return
    rel, data = found
    columns = _section(data, "items", "usecase", "columns") or {}
    for loaded in ctx.terminals():
        terminal = str((spec(loaded).get("metadata") or {}).get("id"))
        if terminal not in columns:
            yield ctx.finding(
                "V-33", rel, "/items/usecase/columns", f"terminal {terminal} has no column"
            )
    seen: dict[str, str] = {}
    for terminal, column in columns.items():
        if column in seen:
            yield ctx.finding(
                "V-33",
                rel,
                f"/items/usecase/columns/{terminal}",
                f"column {column!r} is also used by {seen[column]}",
            )
        seen[column] = terminal


@REGISTRY.rule(
    "V-34",
    "L4",
    "error",
    "Every run state has an item state and a sub-stage in the tracker mapping",
)
def v34_run_states(ctx: Context) -> Iterator[Finding]:
    found = _mapping(ctx)
    if found is None:
        return
    rel, data = found
    states = _section(data, "items", "run", "states") or {}
    sub_stages = data.get("sub_stages") or {}
    for state in RunState:
        if state.value not in states:
            yield ctx.finding(
                "V-34", rel, "/items/run/states", f"run state {state.value} has no item state"
            )
        if state.value not in sub_stages:
            yield ctx.finding(
                "V-34", rel, "/sub_stages", f"run state {state.value} has no sub-stage"
            )


@REGISTRY.rule(
    "V-35",
    "L4",
    "error",
    "Every human outcome and board action has a distinct decision value in the tracker mapping",
)
def v35_decision_values(ctx: Context) -> Iterator[Finding]:
    found = _mapping(ctx)
    if found is None:
        return
    rel, data = found
    values = _section(data, "decision", "values") or {}
    needed: dict[str, str] = {action: "the board" for action in BOARD_ACTIONS}
    for loaded in ctx.terminals():
        t = spec(loaded)
        terminal = str((t.get("metadata") or {}).get("id"))
        rights = _section(t, "authorities", "status_rights", "human") or []
        for outcome in rights:
            needed.setdefault(str(outcome), f"terminal {terminal}")
    for action, source in needed.items():
        if action not in values:
            yield ctx.finding(
                "V-35",
                rel,
                "/decision/values",
                f"{action} (needed by {source}) has no decision value",
            )
    seen: dict[str, str] = {}
    for action, value in values.items():
        key = str(value).strip().lower()
        if key in seen:
            yield ctx.finding(
                "V-35",
                rel,
                f"/decision/values/{action}",
                f"decision value {value!r} is also used by {seen[key]}",
            )
        seen[key] = action


@REGISTRY.rule(
    "V-36",
    "L4",
    "error",
    "Tracker mapping fields are distinct and platform-written fields are mapped",
)
def v36_fields(ctx: Context) -> Iterator[Finding]:
    found = _mapping(ctx)
    if found is None:
        return
    rel, data = found
    decision = data.get("decision") or {}
    inputs = decision.get("inputs") or {}
    owners: dict[str, str] = {}
    labels: dict[str, str] = {}
    candidates = [
        ("/decision/field", "decision", decision.get("field")),
        ("/decision/comment", "comment", decision.get("comment")),
        *(
            (f"/decision/inputs/{name}/field", name, (spec_ or {}).get("field"))
            for name, spec_ in inputs.items()
        ),
    ]
    for pointer, owner, field in candidates:
        if field is None:
            continue
        if field in owners:
            yield ctx.finding(
                "V-36", rel, pointer, f"field {field} is also used for {owners[field]}"
            )
        owners[field] = owner
    for name, spec_ in inputs.items():
        label = str((spec_ or {}).get("label", "")).strip().lower()
        if label in labels:
            yield ctx.finding(
                "V-36",
                rel,
                f"/decision/inputs/{name}/label",
                f"label {label!r} is also used by {labels[label]}",
            )
        labels[label] = name
    written = data.get("platform_written") or {}
    for kind, names in written.items():
        mapped = _section(data, "items", kind, "fields") or {}
        for i, name in enumerate(names or []):
            if name not in mapped:
                yield ctx.finding(
                    "V-36",
                    rel,
                    f"/platform_written/{kind}/{i}",
                    f"platform-written field {name} is not a mapped {kind} field",
                )
