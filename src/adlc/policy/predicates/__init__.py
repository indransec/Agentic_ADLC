"""Predicate library bound to ``adlc-specs/shared/predicates.yaml`` (FR-002).

Each module registers its predicates with ``@predicate(name, arity)``. ``check_catalogue``
compares the registry with the catalogue; the engine refuses to start on any difference.
"""

import importlib
from collections.abc import Callable, Mapping
from typing import Any

PredicateFn = Callable[..., Any]
REGISTRY: dict[str, tuple[PredicateFn, int]] = {}
MODULES = ("records", "tables", "design", "evaluation", "operations", "change")


def predicate(name: str, arity: int) -> Callable[[PredicateFn], PredicateFn]:
    def register(fn: PredicateFn) -> PredicateFn:
        if name in REGISTRY:
            raise ValueError(f"predicate {name} registered twice")
        REGISTRY[name] = (fn, arity)
        return fn

    return register


def load_all() -> dict[str, tuple[PredicateFn, int]]:
    """Import every predicate module (registration happens on import)."""
    for module in MODULES:
        importlib.import_module(f"{__name__}.{module}")
    return REGISTRY


def check_catalogue(
    catalogue: Mapping[str, Any], registry: Mapping[str, tuple[PredicateFn, int]]
) -> list[str]:
    """Problems between the catalogue and the registry; empty when they match exactly."""
    expected = {str(p["name"]): len(p.get("params") or []) for p in catalogue.get("predicates", [])}
    problems = [f"missing predicate {n}" for n in sorted(set(expected) - set(registry))]
    problems += [
        f"predicate {n} is not in the catalogue" for n in sorted(set(registry) - set(expected))
    ]
    problems += [
        f"predicate {n} takes {registry[n][1]} arguments, catalogue says {expected[n]}"
        for n in sorted(set(expected) & set(registry))
        if registry[n][1] != expected[n]
    ]
    return problems
