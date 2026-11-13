"""Artifacts the platform builds from records (011 FR-003; 012 research R-09).

An agent never writes these; the evidence provider builds them when a terminal's record is read:

- ``signed_record``: the people's sign-offs (pass or exception) on the run;
- ``baseline``: one measured number from an evidence source, with the spec's tolerance;
- ``gate_summary``: the status, signers and open waivers of every other terminal of the use case.

What a baseline is built from (source, field, tolerance) is spec content (``built_from``).
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

SIGNED_DECISIONS = ("pass", "exception")


def signed_record(sign_offs: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"role": s["role"], "decision": s["decision"], "date": str(s["signed_at"])[:10]}
        for s in sign_offs
        if s["decision"] in SIGNED_DECISIONS
    ]


def _at(value: Any, path: str) -> Any:
    for name in path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(name)
    return value


def baseline(built_from: Mapping[str, Any], evidence: Any) -> list[dict[str, Any]] | None:
    """The baseline row, or ``None`` when the source has no measured number (fails closed)."""
    field = str(built_from["field"])
    value = _at(evidence, field)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return [
        {
            "metric": field.rsplit(".", 1)[-1],
            "value": value,
            "tolerance": float(built_from["tolerance"]),
        }
    ]


@dataclass(frozen=True)
class GateRecord:
    terminal: str
    status: str
    signed_by: Sequence[str]
    closed_at: datetime | None
    waivers: Sequence[tuple[str, str]]  # (waiver id, expiry)


def _number(terminal: str) -> tuple[int, str]:
    found = re.search(r"\d+", terminal)
    return (int(found.group()) if found else 0, terminal)


def gate_summary(records: Iterable[GateRecord]) -> list[dict[str, Any]]:
    rows = []
    for r in sorted(records, key=lambda r: _number(r.terminal)):
        expiries = sorted(e for _, e in r.waivers if e)
        rows.append(
            {
                "terminal": r.terminal,
                "status": r.status,
                "signed_by": ", ".join(r.signed_by),
                "date": r.closed_at.date().isoformat() if r.closed_at else "",
                "open_waivers": ", ".join(w for w, _ in r.waivers),
                "waiver_expiry": expiries[0] if expiries else "",
            }
        )
    return rows
