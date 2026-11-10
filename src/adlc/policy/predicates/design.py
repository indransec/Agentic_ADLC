"""Design and build predicates (contracts/predicates.md)."""

import re
from typing import Any

from adlc.policy.predicates import predicate
from adlc.policy.predicates.context import catalogue_items, fail, name_of, ok, rows
from adlc.policy.values import as_number, is_empty, is_truthy, text, to_py

NEW_TOOL = "new"


def _ids(value: Any) -> set[str]:
    plain = to_py(value)
    if isinstance(plain, list):
        return {str(v).strip() for v in plain if str(v).strip()}
    return {part for part in re.split(r"[,\s;]+", text(plain)) if part}


@predicate("every_req_mapped", 2)
def every_req_mapped(requirements: Any, decisions: Any) -> Any:
    mapped: set[str] = set()
    for row in rows(decisions):
        mapped |= _ids(row.get("req_ids"))
    for i, row in enumerate(rows(requirements), start=1):
        req = text(row.get("req_id"))
        if req not in mapped:
            return fail(
                f"{name_of(requirements)} row {i}: {req} is not mapped in {name_of(decisions)}"
            )
    return ok()


@predicate("every_req_traced", 3)
def every_req_traced(requirements: Any, trace: Any, column: Any) -> Any:
    col = text(column)
    traced = {text(r.get("req_id")) for r in rows(trace) if not is_empty(r.get(col))}
    for i, row in enumerate(rows(requirements), start=1):
        req = text(row.get("req_id"))
        if req not in traced:
            return fail(f"{name_of(requirements)} row {i}: {req} has no {col} in {name_of(trace)}")
    return ok()


@predicate("all_tools_registered_or_flagged", 1)
def all_tools_registered_or_flagged(contracts: Any) -> Any:
    known = {str(s["id"]) for s in catalogue_items("mcp_servers", "mcp_servers")}
    for i, row in enumerate(rows(contracts), start=1):
        server = text(row.get("mcp_server"))
        if server not in known and server != NEW_TOOL:
            return fail(
                f"{name_of(contracts)} row {i}: {server!r} is not a registered MCP server or {NEW_TOOL!r}"
            )
    return ok()


def _category(row: dict[str, Any], category: str) -> bool:
    return text(row.get("category")).lower() == category


@predicate("token_budget_within_nfr", 2)
def token_budget_within_nfr(budget: Any, nfrs: Any) -> Any:
    budget_rows = rows(budget)
    if not budget_rows:
        return fail(f"{name_of(budget)} is empty")
    targets = [as_number(r.get("target")) for r in rows(nfrs) if _category(r, "cost")]
    limit = min((t for t in targets if t is not None), default=None)
    for i, row in enumerate(budget_rows, start=1):
        tokens, cost = as_number(row.get("max_tokens")), as_number(row.get("max_cost_usd"))
        if tokens is None or cost is None:
            return fail(f"{name_of(budget)} row {i}: max_tokens and max_cost_usd must be numeric")
        if limit is not None and cost > limit:
            return fail(
                f"{name_of(budget)} row {i}: max_cost_usd {cost} is above the cost NFR {limit}"
            )
    return ok()


@predicate("data_classes_within", 2)
def data_classes_within(strategy: Any, approval: Any) -> Any:
    ranks = {str(c["id"]): int(c["rank"]) for c in catalogue_items("data_classes", "data_classes")}
    approved = [
        ranks.get(text(r.get("classification")), 0)
        for r in rows(approval)
        if text(r.get("access_status")).lower() == "approved"
    ]
    ceiling = max(approved, default=0)
    for i, row in enumerate(rows(strategy), start=1):
        cls = text(row.get("classification"))
        if cls not in ranks:
            return fail(f"{name_of(strategy)} row {i}: {cls!r} is not a data class")
        if ranks[cls] > ceiling:
            return fail(f"{name_of(strategy)} row {i}: {cls} is above the approved classification")
    return ok()


@predicate("hitl_covered", 2)
def hitl_covered(autonomy: Any, hitl: Any) -> Any:
    designed = {text(r.get("action")) for r in rows(hitl)}
    for i, row in enumerate(rows(autonomy), start=1):
        if is_truthy(row.get("hitl_required")) and text(row.get("action")) not in designed:
            return fail(
                f"{name_of(autonomy)} row {i}: {row.get('action')!r} has no HITL design row"
            )
    return ok()


@predicate("scan_clean", 3)
def scan_clean(checks: Any, scan: Any, levels: Any) -> Any:
    wanted = text(scan)
    for row in rows(checks):
        if text(row.get("scan")) == wanted:
            for level in [str(lv) for lv in to_py(levels)]:
                count = as_number(row.get(f"{level}_count"))
                if count is None or count != 0:
                    return fail(
                        f"{name_of(checks)}: {wanted} has {row.get(f'{level}_count')!r} {level} findings"
                    )
            return ok()
    return fail(f"{name_of(checks)}: no {wanted} scan")


@predicate("permissions_subset", 2)
def permissions_subset(matrix: Any, design: Any) -> Any:
    designed: set[str] = set()
    for row in rows(design):
        designed |= {text(row.get("control")), text(row.get("layer"))}
    designed.discard("")
    for i, row in enumerate(rows(matrix), start=1):
        resource = text(row.get("resource"))
        if resource not in designed:
            return fail(f"{name_of(matrix)} row {i}: {resource!r} is not in the designed controls")
    return ok()


@predicate("any_design_deviation", 1)
def any_design_deviation(conformance: Any) -> Any:
    for row in rows(conformance):
        deviation = text(row.get("deviation")).lower()
        if deviation and deviation != "none":
            return ok()
    return fail(f"{name_of(conformance)}: no design deviation")
