"""Change classification predicates (contracts/predicates.md), using the change class catalogue."""

import re
from typing import Any

from adlc.policy.predicates import predicate
from adlc.policy.predicates.context import (
    PredicateError,
    catalogue_items,
    current,
    fail,
    name_of,
    ok,
    rows,
)
from adlc.policy.values import text, to_py

_TERMINAL_NUMBER = re.compile(r"^[A-Z]([0-9]+)$")


def _ranks() -> dict[str, int]:
    return {
        str(c["id"]): int(c["rank"]) for c in catalogue_items("change_classes", "change_classes")
    }


def _number(terminal: str) -> int:
    match = _TERMINAL_NUMBER.match(terminal)
    if match is None:
        raise PredicateError(f"{terminal!r} is not a terminal")
    return int(match.group(1))


def _class_reentry() -> dict[str, str]:
    """Each change class's re-entry terminal, from the pinned spec of the run's terminal."""
    spec = current().spec or {}
    body = spec.get("terminal", spec)
    classes = body.get("change_classes") if isinstance(body, dict) else None
    return {
        str(k): str(v["reentry"])
        for k, v in (classes or {}).items()
        if isinstance(v, dict) and v.get("reentry")
    }


@predicate("reentry_consistent", 1)
def reentry_consistent(assessment: Any) -> Any:
    ranks, reentry = _ranks(), _class_reentry()
    found = rows(assessment)
    if not found:
        return fail(f"{name_of(assessment)} is empty")
    for i, row in enumerate(found, start=1):
        cls, terminal = text(row.get("change_class")), text(row.get("reentry_terminal"))
        if cls not in ranks:
            return fail(f"{name_of(assessment)} row {i}: {cls!r} is not a change class")
        if cls in reentry and _number(terminal) > _number(reentry[cls]):
            return fail(
                f"{name_of(assessment)} row {i}: re-entry {terminal} is later than {reentry[cls]} for {cls}"
            )
    return ok()


@predicate("class_at_least_if", 3)
def class_at_least_if(assessment: Any, components: Any, minimum: Any) -> Any:
    ranks = _ranks()
    floor = ranks.get(text(minimum))
    if floor is None:
        raise PredicateError(f"{text(minimum)!r} is not a change class")
    watched = {str(c).lower() for c in to_py(components)}
    for i, row in enumerate(rows(assessment), start=1):
        affected = {
            p.strip().lower()
            for p in re.split(r"[,;]", text(row.get("affected_components")))
            if p.strip()
        }
        if affected & watched and ranks.get(text(row.get("change_class")), 0) < floor:
            return fail(
                f"{name_of(assessment)} row {i}: {sorted(affected & watched)} changed, class below {text(minimum)}"
            )
    return ok()


@predicate("classification_disputed", 1)
def classification_disputed(assessment: Any) -> Any:
    classes = {text(r.get("change_class")) for r in rows(assessment)}
    return ok() if len(classes) > 1 else fail(f"{name_of(assessment)}: one change class")


@predicate("has_change_class", 2)
def has_change_class(assessment: Any, change_class: Any) -> Any:
    wanted = text(change_class)
    for row in rows(assessment):
        if text(row.get("change_class")) == wanted:
            return ok()
    return fail(f"{name_of(assessment)}: no {wanted} change")
