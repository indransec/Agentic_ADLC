"""Pure routing decisions over pinned specs (research R-05, R-06; FR-014 to FR-020).

Event names follow SA Annex A.3: ``<terminal>.<status>``, ``<terminal>.rework.<root_cause>``,
``<terminal>.reentry.<terminal>``, ``<terminal>.event.<name>``. Nothing here names a terminal.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from adlc.orchestration import spec_view
from adlc.orchestration.spec_view import Spec

_TEMPLATE = re.compile(
    r"^\$\{(?P<terminal>[A-Z][0-9]+)\.(?P<artifact>[a-z0-9_]+)\.(?P<column>[a-z0-9_]+)\}$"
)


def _parts(event_type: str) -> list[str]:
    return event_type.split(".")


def is_rework_event(event_type: str) -> bool:
    parts = _parts(event_type)
    return len(parts) >= 2 and parts[1] == "rework"


def is_terminate_event(event_type: str) -> bool:
    parts = _parts(event_type)
    return len(parts) == 2 and parts[1] == "terminate"


def event_source(event_type: str) -> str:
    return _parts(event_type)[0]


def outcome_event_type(
    terminal_id: str, status: str, root_cause: str | None = None, reentry: str | None = None
) -> str:
    if reentry is not None:
        return f"{terminal_id}.reentry.{reentry}"
    if status == "rework":
        return f"{terminal_id}.rework.{root_cause}"
    return f"{terminal_id}.{status}"


def operational_event_type(terminal_id: str, name: str) -> str:
    return f"{terminal_id}.event.{name}"


def escalate_event_type(terminal_id: str) -> str:
    return f"{terminal_id}.escalate"


def subscribers(pinned: Mapping[str, Spec], event_type: str) -> tuple[str, ...]:
    """Terminals whose pinned spec subscribes to ``event_type`` (FR-015)."""
    return tuple(
        sorted(tid for tid, spec in pinned.items() if event_type in spec_view.triggers(spec))
    )


def run_mode(trigger_event_type: str) -> str:
    """``retire`` when the run was opened by a terminate event, else ``evolve`` (FR-009b)."""
    return "retire" if is_terminate_event(trigger_event_type) else "evolve"


def rework_count(previous_trigger_types: Sequence[str], event_type: str) -> int:
    """Reworks routed to a terminal, including this event if it is one (FR-019, research R-05)."""
    earlier = sum(1 for t in previous_trigger_types if is_rework_event(t))
    return earlier + (1 if is_rework_event(event_type) else 0)


def over_rework_limit(count: int, max_rework_cycles: int) -> bool:
    return count > max_rework_cycles


def is_template(destination: str) -> bool:
    return destination.startswith("${")


def resolve_template(
    destination: str, terminal_id: str, artifacts: Mapping[str, Any]
) -> str | None:
    """``${T<n>.<artifact>.<column>}`` from the closing run's artifacts (first row)."""
    match = _TEMPLATE.match(destination)
    if match is None or match["terminal"] != terminal_id:
        return None
    rows = artifacts.get(match["artifact"])
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], Mapping):
        return None
    value = rows[0].get(match["column"])
    return None if value is None else str(value)


@dataclass(frozen=True)
class Emitted:
    values: dict[str, Any]
    missing: tuple[str, ...]


def emitted_values(
    spec: Spec,
    artifacts: Mapping[str, Any],
    run_attributes: Mapping[str, Any],
    provided: Mapping[str, Any],
) -> Emitted:
    """Values a pass emits (FR-018a): decision fields, then artifacts, then known run values.

    An emitted name that is an artifact is referenced; ``artifact.column`` takes the first row's
    value; any other name must be supplied by the deciding person unless the run already knows it.
    """
    values: dict[str, Any] = {}
    missing: list[str] = []
    for name in spec_view.emits(spec):
        artifact, _, column = name.partition(".")
        if name in provided and provided[name] not in (None, ""):
            values[name] = provided[name]
        elif not column and artifact in artifacts:
            values[name] = {"artifact": artifact}
        elif column and isinstance(artifacts.get(artifact), list) and artifacts[artifact]:
            values[name] = artifacts[artifact][0].get(column)
        elif run_attributes.get(name) not in (None, ""):
            values[name] = run_attributes[name]
        else:
            missing.append(name)
    return Emitted(values, tuple(missing))
