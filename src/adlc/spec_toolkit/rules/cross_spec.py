"""L4 rules: references across files and catalogues (contracts/validation-rules.md).

Rules iterate over whatever specs and catalogues declare; no terminal, role or event name is
written in this module (constitution I).
"""

import re
from collections.abc import Iterator
from typing import Any

from adlc.spec_toolkit.catalogues import Catalogues
from adlc.spec_toolkit.findings import Finding
from adlc.spec_toolkit.rules import REGISTRY, Context

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


# ------------------------------------------------- composite rules (more parts land in US1)


@REGISTRY.rule("V-01", "L4", "error", "Ids unique within a spec, terminal ids unique across files")
def v01_unique_ids(ctx: Context) -> Iterator[Finding]:
    yield from catalogue_duplicates(ctx)


@REGISTRY.rule("V-18", "L4", "error", "SA Annex A naming for ids, names and catalogue entries")
def v18_naming(ctx: Context) -> Iterator[Finding]:
    yield from catalogue_naming(ctx)
