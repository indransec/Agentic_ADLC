"""The SA §12.3 KPIs (feature 013, research R-05), as pure formulas over a use case's records.

Each KPI has an id, name, definition, unit and value; a rate whose denominator is zero (or a
duration with nothing measured) is ``None``, shown as "no data", never zero (FR-004). The
portfolio pools the same records across use cases (``pool``).
"""

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from adlc.dashboard.timesplit import CATEGORIES, Transition, split

DECIDABLE = ("pass", "rework", "exception", "terminate")  # analysis A4
SIGNED = ("pass", "exception")


@dataclass(frozen=True)
class RunFact:
    run_id: str
    terminal_id: str
    run_number: int
    final_status: str | None
    opened_at: datetime
    closed_at: datetime | None
    recommendation: str | None = None
    expected_seconds: float | None = None  # the spec timeline's expected duration for the tier
    blocking_controls: tuple[str, ...] = ()


@dataclass(frozen=True)
class SignOff:
    run_id: str
    decision: str
    root_cause: str | None


@dataclass(frozen=True)
class Round:
    run_id: str
    role: str
    asked_at: datetime
    answered_at: datetime | None


@dataclass(frozen=True)
class ArtifactVersion:
    run_id: str
    artifact_id: str
    version: int
    producer_type: str


@dataclass(frozen=True)
class ControlDecision:
    run_id: str
    check_id: str
    attempt: int
    passed: bool


@dataclass(frozen=True)
class Records:
    submitted_at: datetime
    closed_at: datetime | None
    now: datetime
    runs: Sequence[RunFact]
    transitions: Mapping[str, Sequence[Transition]]
    sign_offs: Sequence[SignOff]
    rounds: Sequence[Round]
    escalations: Sequence[tuple[str, str | None]]  # (run id, trigger) per escalation
    artifact_versions: Sequence[ArtifactVersion]
    control_decisions: Sequence[ControlDecision]
    extra: Mapping[str, Any] = field(default_factory=dict)


KPI_IDS = (
    "elapsed",
    "time_split",
    "reworks",
    "clarifications",
    "clarification_wait",
    "first_pass_yield",
    "escalations",
    "reviewer_agreement",
    "human_edit_rate",
    "control_first_pass",
    "sla_adherence",
)
DEFINITIONS = {
    "elapsed": ("Lifecycle elapsed time", "seconds", True, "Use case submitted to closed, or now"),
    "time_split": (
        "Time per terminal, split",
        "split",
        False,
        "Agent working, reviewer, waiting for clarification, waiting for people, blocked",
    ),
    "reworks": ("Reworks", "count", True, "Rework decisions, per terminal by root cause"),
    "clarifications": (
        "Clarifications",
        "count",
        True,
        "Clarification rounds, per terminal by addressed role",
    ),
    "clarification_wait": (
        "Clarification wait",
        "seconds",
        False,
        "Mean time from question to answer (answered rounds)",
    ),
    "first_pass_yield": (
        "First-pass yield",
        "ratio",
        True,
        "Terminals whose first run closed pass or exception / terminals whose first run closed",
    ),
    "escalations": ("Escalations", "count", True, "Escalations, with terminal, run and trigger"),
    "reviewer_agreement": (
        "Reviewer–human agreement",
        "ratio",
        False,
        "Decisions equal to the reviewer's recommendation / decisions where it recommended an "
        "outcome a person can decide (an escalate recommendation is not counted)",
    ),
    "human_edit_rate": (
        "Human edit rate",
        "ratio",
        False,
        "Agent artifacts a person changed in the same run / agent artifacts",
    ),
    "control_first_pass": (
        "Control first-time pass rate",
        "ratio",
        False,
        "Blocking controls passed at the first attempt / blocking controls at the first attempt",
    ),
    "sla_adherence": (
        "SLA adherence",
        "ratio",
        True,
        "Closed runs within the terminal's expected duration for the tier / closed runs with one",
    ),
}


def _kpi(kid: str, value: Any, **more: Any) -> dict[str, Any]:
    name, unit, headline, definition = DEFINITIONS[kid]
    return {
        "id": kid,
        "name": name,
        "unit": unit,
        "headline": headline,
        "definition": definition,
        "value": value,
        **more,
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def compute(r: Records) -> list[dict[str, Any]]:
    terminal_of = {run.run_id: run.terminal_id for run in r.runs}
    # time split per terminal
    per_terminal: dict[str, dict[str, float]] = defaultdict(lambda: dict.fromkeys(CATEGORIES, 0.0))
    for run in r.runs:
        for category, seconds in split(r.transitions.get(run.run_id, ()), now=r.now).items():
            per_terminal[run.terminal_id][category] += seconds
    totals = dict.fromkeys(CATEGORIES, 0.0)
    for values in per_terminal.values():
        for category, seconds in values.items():
            totals[category] += seconds
    # reworks and clarifications
    reworks: dict[str, Counter[str]] = defaultdict(Counter)
    for s in r.sign_offs:
        if s.decision == "rework":
            reworks[terminal_of.get(s.run_id, "?")][s.root_cause or "unspecified"] += 1
    rounds: dict[str, Counter[str]] = defaultdict(Counter)
    waits: dict[str, list[float]] = defaultdict(list)
    for c in r.rounds:
        terminal = terminal_of.get(c.run_id, "?")
        rounds[terminal][c.role] += 1
        if c.answered_at is not None:
            waits[terminal].append((c.answered_at - c.asked_at).total_seconds())
    every_wait = [w for found in waits.values() for w in found]
    # first-pass yield
    firsts = [run for run in r.runs if run.run_number == 1 and run.closed_at is not None]
    # reviewer agreement
    recommended = {run.run_id: run.recommendation for run in r.runs}
    counted = [s for s in r.sign_offs if recommended.get(s.run_id) in DECIDABLE]
    # human edits: (run, artifact) pairs with an agent version; edited if a person version exists
    agent_made = {
        (v.run_id, v.artifact_id) for v in r.artifact_versions if v.producer_type == "agent"
    }
    edited = {
        (v.run_id, v.artifact_id)
        for v in r.artifact_versions
        if v.producer_type == "person" and (v.run_id, v.artifact_id) in agent_made
    }
    # controls at the first attempt (blocking only)
    blocking = {run.run_id: set(run.blocking_controls) for run in r.runs}
    first: dict[tuple[str, str], bool] = {}
    for d in sorted(r.control_decisions, key=lambda d: d.attempt):
        if d.attempt == 1 and d.check_id in blocking.get(d.run_id, set()):
            first.setdefault((d.run_id, d.check_id), d.passed)
    # SLA
    timed = [
        run for run in r.runs if run.closed_at is not None and run.expected_seconds is not None
    ]
    within = [
        run
        for run in timed
        if run.closed_at is not None
        and run.expected_seconds is not None
        and (run.closed_at - run.opened_at).total_seconds() <= run.expected_seconds
    ]
    return [
        _kpi("elapsed", ((r.closed_at or r.now) - r.submitted_at).total_seconds()),
        _kpi(
            "time_split", totals, per_terminal={t: dict(v) for t, v in sorted(per_terminal.items())}
        ),
        _kpi(
            "reworks",
            sum(sum(c.values()) for c in reworks.values()),
            per_terminal={t: dict(c) for t, c in sorted(reworks.items())},
        ),
        _kpi(
            "clarifications",
            len(r.rounds),
            per_terminal={t: dict(c) for t, c in sorted(rounds.items())},
        ),
        _kpi(
            "clarification_wait",
            sum(every_wait) / len(every_wait) if every_wait else None,
            per_terminal={t: sum(w) / len(w) for t, w in sorted(waits.items()) if w},
        ),
        _kpi(
            "first_pass_yield",
            _ratio(sum(1 for run in firsts if run.final_status in SIGNED), len(firsts)),
        ),
        _kpi(
            "escalations",
            len(r.escalations),
            detail=[
                {"run_id": run_id, "terminal_id": terminal_of.get(run_id, "?"), "trigger": trigger}
                for run_id, trigger in r.escalations
            ],
        ),
        _kpi(
            "reviewer_agreement",
            _ratio(sum(1 for s in counted if s.decision == recommended[s.run_id]), len(counted)),
        ),
        _kpi("human_edit_rate", _ratio(len(edited), len(agent_made))),
        _kpi("control_first_pass", _ratio(sum(first.values()), len(first))),
        _kpi("sla_adherence", _ratio(len(within), len(timed))),
    ]


def pool(records: Iterable[Records], now: datetime) -> list[dict[str, Any]]:
    """Portfolio KPIs: the same formulas over every use case's records together (counts and
    times summed, rates pooled, never a mean of rates); elapsed is the mean per use case."""
    found = list(records)
    merged = Records(
        submitted_at=now,
        closed_at=now,
        now=now,
        runs=[run for r in found for run in r.runs],
        transitions={k: v for r in found for k, v in r.transitions.items()},
        sign_offs=[s for r in found for s in r.sign_offs],
        rounds=[c for r in found for c in r.rounds],
        escalations=[e for r in found for e in r.escalations],
        artifact_versions=[v for r in found for v in r.artifact_versions],
        control_decisions=[d for r in found for d in r.control_decisions],
    )
    kpis = compute(merged)
    elapsed = [((r.closed_at or r.now) - r.submitted_at).total_seconds() for r in found]
    kpis[0] = _kpi(
        "elapsed",
        sum(elapsed) / len(elapsed) if elapsed else None,
        definition_note="mean per use case",
    )
    return kpis
