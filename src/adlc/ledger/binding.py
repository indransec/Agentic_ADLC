"""``evidence.ledger.bound_to`` resolved in a use case (FR-003; shared with feature 004)."""

import re
from collections.abc import Callable, Mapping
from typing import Any

from adlc.orchestration import spec_view

_TERMINAL = re.compile(r"^[A-Z][0-9]+$")


def bound_reference(spec: Mapping[str, Any]) -> tuple[str, tuple[str, ...]] | None:
    """(terminal, path) of the spec's binding, or None when it has none."""
    ledger = (spec_view.body(spec).get("evidence") or {}).get("ledger") or {}
    reference = ledger.get("bound_to") if isinstance(ledger, Mapping) else None
    if not isinstance(reference, str):
        return None
    root, *path = reference.split(".")
    if not _TERMINAL.match(root) or not path:
        return None
    return root, tuple(path)


def resolve_bound_to(
    spec: Mapping[str, Any], record_of: Callable[[str], Mapping[str, Any] | None]
) -> Any:
    """Follow the binding through ``record_of(terminal)`` (a table reads its first row)."""
    reference = bound_reference(spec)
    if reference is None:
        return None
    terminal, path = reference
    value: Any = record_of(terminal)
    for member in path:
        if isinstance(value, list):
            value = value[0] if value and isinstance(value[0], Mapping) else None
        if not isinstance(value, Mapping) or member not in value:
            return None
        value = value[member]
    return value
