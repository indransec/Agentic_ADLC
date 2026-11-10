"""Spec → projection rows the orchestrator reads (data-model.md; pure, no database).

Used by registration (rows inserted with the registry entry) and by the in-memory registry,
so both always give the same answers.
"""

from dataclasses import dataclass
from typing import Any

from adlc.spec_toolkit.catalogues import Catalogues
from adlc.spec_toolkit.graph import classify, emitted_events

TIERS = ("low", "medium", "high")
STATUSES = ("pass", "rework", "exception", "escalate", "terminate")


@dataclass(frozen=True)
class OutcomeRoute:
    outcome_status: str
    root_cause: str | None
    destination_kind: str
    destination: str
    alternatives: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    recheck_at: tuple[str, ...] = ()
    set_by: tuple[str, ...] = ()
    notify: tuple[str, ...] = ()
    condition: str | None = None


@dataclass(frozen=True)
class EventRoute:
    event_type: str
    destination_kind: str
    destination: str
    immediate: tuple[str, ...] = ()
    then_destination: str | None = None
    notify: tuple[str, ...] = ()
    condition: str | None = None


@dataclass(frozen=True)
class ChangeClass:
    change_class: str
    reentry_terminal: str
    path: tuple[str, ...] = ()
    retrospective: tuple[str, ...] = ()
    within: str | None = None
    alternative: str | None = None


@dataclass(frozen=True)
class Timeline:
    risk_tier: str
    expected_duration: str | None
    continuous: bool
    reminder_after: str
    escalate_after: str | None
    escalate_at_window_end: bool
    max_rework_cycles: int
    clarification_sla: str
    max_clarification_rounds: int
    max_auto_retries: int | None
    retirement_duration: str | None


@dataclass(frozen=True)
class Projection:
    terminal_id: str
    triggers: tuple[str, ...]
    emitted_events: tuple[str, ...]
    outcome_routes: tuple[OutcomeRoute, ...]
    event_routes: tuple[EventRoute, ...]
    change_classes: tuple[ChangeClass, ...]
    timelines: tuple[Timeline, ...]


def _strs(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(v) for v in value)
    if isinstance(value, str):
        return (value,)
    return ()


def _tiered(value: Any, tier: str) -> Any:
    return value.get(tier) if isinstance(value, dict) else value


def _route_row(
    status: str, outcome: dict[str, Any], cause: str | None, kind: str, dest: str
) -> OutcomeRoute:
    when = outcome.get("when")
    return OutcomeRoute(
        outcome_status=status,
        root_cause=cause,
        destination_kind=kind,
        destination=dest,
        alternatives=_strs(outcome.get("alternatives")),
        requires=_strs(outcome.get("requires")),
        recheck_at=_strs(outcome.get("recheck_at")),
        set_by=_strs(outcome.get("set_by")),
        notify=_strs(outcome.get("notify")),
        condition=when if isinstance(when, str) else None,
    )


def _outcome_routes(t: dict[str, Any], cats: Catalogues, known: set[str]) -> list[OutcomeRoute]:
    rows: list[OutcomeRoute] = []
    model = t.get("outcome_model") or {}
    for status in STATUSES:
        outcome = model.get(status) or {}
        if outcome.get("not_allowed"):
            rows.append(_route_row(status, outcome, None, "disabled", ""))
            continue
        for cause, dest in (outcome.get("route_by_root_cause") or {}).items():
            kind = classify(str(dest), cats, known).kind
            rows.append(_route_row(status, outcome, str(cause), kind, str(dest)))
        route = outcome.get("route")
        if isinstance(route, str):
            rows.append(_route_row(status, outcome, None, classify(route, cats, known).kind, route))
        elif status == "terminate" and not outcome.get("route_by_root_cause"):
            rows.append(_route_row(status, outcome, None, "terminating", ""))
    return rows


def _event_routes(t: dict[str, Any], cats: Catalogues, known: set[str]) -> list[EventRoute]:
    rows: list[EventRoute] = []
    for event, route in ((t.get("outcome_model") or {}).get("event_routes") or {}).items():
        route = route or {}
        dest = str(route.get("route", ""))
        then = route.get("then")
        rows.append(
            EventRoute(
                event_type=str(event),
                destination_kind=classify(dest, cats, known).kind,
                destination=dest,
                immediate=_strs(route.get("immediate")),
                then_destination=str(then) if isinstance(then, str) else None,
                notify=_strs(route.get("notify")),
                condition=route.get("then_when"),
            )
        )
    return rows


def _change_classes(t: dict[str, Any]) -> list[ChangeClass]:
    rows: list[ChangeClass] = []
    for name, change in (t.get("change_classes") or {}).items():
        change = change or {}
        alternative = change.get("alternative")
        within = change.get("within")
        rows.append(
            ChangeClass(
                change_class=str(name),
                reentry_terminal=str(change.get("reentry")),
                path=_strs(change.get("path")),
                retrospective=_strs(change.get("retrospective")),
                within=str(within) if within is not None else None,
                alternative=str(alternative) if alternative is not None else None,
            )
        )
    return rows


def _timelines(t: dict[str, Any]) -> list[Timeline]:
    timeline = t.get("timeline") or {}
    expected = timeline.get("expected_duration")
    continuous = expected == "continuous"
    escalate = timeline.get("escalate_after")
    retries = timeline.get("max_auto_retries")
    rows: list[Timeline] = []
    for tier in TIERS:
        retirement = _tiered(timeline.get("retirement_duration"), tier)
        rows.append(
            Timeline(
                risk_tier=tier,
                expected_duration=None if continuous else str(_tiered(expected, tier)),
                continuous=continuous,
                reminder_after=str(timeline.get("reminder_after")),
                escalate_after=None if escalate == "window_end" else str(escalate),
                escalate_at_window_end=escalate == "window_end",
                max_rework_cycles=int(timeline.get("max_rework_cycles", 0)),
                clarification_sla=str(timeline.get("clarification_sla")),
                max_clarification_rounds=int(timeline.get("max_clarification_rounds", 0)),
                max_auto_retries=int(retries) if retries is not None else None,
                retirement_duration=str(retirement) if retirement is not None else None,
            )
        )
    return rows


def project(t: dict[str, Any], cats: Catalogues, known_terminals: set[str]) -> Projection:
    """Projection rows for one terminal spec (the ``terminal`` mapping)."""
    tid = str((t.get("metadata") or {}).get("id"))
    triggers = tuple(str(e) for e in (t.get("trigger") or {}).get("on") or [])
    return Projection(
        terminal_id=tid,
        triggers=triggers,
        emitted_events=tuple(sorted(emitted_events(tid, t))),
        outcome_routes=tuple(_outcome_routes(t, cats, known_terminals)),
        event_routes=tuple(_event_routes(t, cats, known_terminals)),
        change_classes=tuple(_change_classes(t)),
        timelines=tuple(_timelines(t)),
    )
