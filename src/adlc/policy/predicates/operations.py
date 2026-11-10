"""Release, rollout and operations predicates (contracts/predicates.md)."""

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from adlc.orchestration import durations
from adlc.policy.evidence import Evidence
from adlc.policy.predicates import predicate
from adlc.policy.predicates.context import PredicateError, current, fail, name_of, ok, rows
from adlc.policy.predicates.evaluation import OPERATORS, _disagree
from adlc.policy.values import as_number, is_empty, is_open_row, is_truthy, text, to_py

HASH_FIELDS = ("sha256", "deployed_hash", "hash")
GOOD = ("pass", "success")
BAD = ("fail", "failed", "breach")


@predicate("alerts_cover", 3)
def alerts_cover(monitoring: Any, kpis: Any, signals: Any) -> Any:
    alerted = {
        text(r.get("signal")) for r in rows(monitoring) if not is_empty(r.get("alert_threshold"))
    }
    needed = [text(r.get("kpi")) for r in rows(kpis)] + [
        text(r.get("signal")) for r in rows(signals)
    ]
    for item in needed:
        if item and item not in alerted:
            return fail(f"{name_of(monitoring)}: no alert for {item!r}")
    return ok()


@predicate("go_no_go_disputed", 1)
def go_no_go_disputed(authorisation: Any) -> Any:
    return _disagree(authorisation)


def _time(value: Any) -> datetime:
    plain = to_py(value)
    if isinstance(plain, datetime):
        return plain
    try:
        return datetime.fromisoformat(text(plain).replace("Z", "+00:00"))
    except ValueError as exc:
        raise PredicateError(f"not a time: {plain!r}") from exc


@predicate("within_window", 1)
def within_window(window: Any) -> Any:
    value = to_py(window)
    if not isinstance(value, dict) or "start" not in value or "end" not in value:
        raise PredicateError(f"{name_of(window)} has no start and end")
    now = current().now
    start, end = _time(value["start"]), _time(value["end"])
    return (
        ok()
        if start <= now <= end
        else fail(f"now ({now:%Y-%m-%d %H:%M}) is outside {start} to {end}")
    )


def _hash(value: Any) -> str:
    plain = to_py(value)
    if isinstance(plain, list) and plain and isinstance(plain[0], dict):
        plain = plain[0]
    if isinstance(plain, dict):
        for field in HASH_FIELDS:
            if not is_empty(plain.get(field)):
                return text(plain[field])
        return ""
    return text(plain)


@predicate("hash_matches", 2)
def hash_matches(a: Any, b: Any) -> Any:
    left, right = _hash(a), _hash(b)
    if not left or not right:
        return fail(f"{name_of(a) if not left else name_of(b)} has no hash")
    return ok() if left == right else fail(f"hash {left} does not match {right}")


def _stage_rows(metrics: Any, stage: Any) -> list[tuple[int, dict[str, Any]]]:
    wanted = text(stage)
    found = [(i, r) for i, r in enumerate(rows(metrics), start=1) if text(r.get("stage")) == wanted]
    if not found:
        raise PredicateError(f"{name_of(metrics)}: no {wanted} stage")
    return found


@predicate("within_baseline_tolerance", 3)
def within_baseline_tolerance(metrics: Any, baseline: Any, stage: Any) -> Any:
    if is_empty(baseline):
        return fail("baseline is not available")
    for i, row in _stage_rows(metrics, stage):
        if text(row.get("result")).lower() != "pass":
            return fail(
                f"{name_of(metrics)} row {i}: {row.get('metric')} result is {row.get('result')!r}"
            )
    return ok()


@predicate("no_breach_in_stage", 2)
def no_breach_in_stage(metrics: Any, stage: Any) -> Any:
    for i, row in _stage_rows(metrics, stage):
        if text(row.get("result")).lower() in BAD:
            return fail(f"{name_of(metrics)} row {i}: {row.get('metric')} breached")
    return ok()


@predicate("rollback_failed", 1)
def rollback_failed(log: Any) -> Any:
    for row in rows(log):
        if (
            "rollback" in text(row.get("stage")).lower()
            and text(row.get("result")).lower() not in GOOD
        ):
            return ok()
    return fail(f"{name_of(log)}: no failed rollback")


@predicate("open_incident", 2)
def open_incident(log: Any, severities: Any) -> Any:
    wanted = {str(s) for s in to_py(severities)}
    for row in rows(log):
        if is_open_row(row) and text(row.get("severity")) in wanted:
            return ok()
    return fail(f"{name_of(log)}: no open incident of {sorted(wanted)}")


def _threshold_row(thresholds: Any, metric: str) -> dict[str, Any]:
    for row in rows(thresholds):
        if text(row.get("metric")) == metric:
            return row
    raise PredicateError(f"{name_of(thresholds)}: no threshold for {metric}")


@predicate("exceeds_threshold", 3)
def exceeds_threshold(signal: Any, thresholds: Any, metric: Any) -> Any:
    row = _threshold_row(thresholds, text(metric))
    value, limit, op = as_number(signal), as_number(row.get("threshold")), text(row.get("operator"))
    if value is None or limit is None or op not in OPERATORS:
        raise PredicateError(f"{metric}: signal, threshold or operator is not usable")
    return ok() if not OPERATORS[op](value, limit) else fail(f"{metric} {value} meets {op} {limit}")


@predicate("below_nfr", 3)
def below_nfr(signal: Any, nfrs: Any, category: Any) -> Any:
    wanted = text(category).lower()
    targets = [
        as_number(r.get("target")) for r in rows(nfrs) if text(r.get("category")).lower() == wanted
    ]
    target = next((t for t in targets if t is not None), None)
    value = as_number(signal)
    if target is None or value is None:
        raise PredicateError(f"no numeric {wanted} NFR or signal")
    return ok() if value < target else fail(f"{wanted} {value} is not below {target}")


def _baseline(value: Any) -> tuple[float, float]:
    plain = to_py(value)
    if isinstance(plain, dict):
        base, tolerance = as_number(plain.get("value")), as_number(plain.get("tolerance")) or 0.0
    else:
        base, tolerance = as_number(plain), 0.0
    if base is None:
        raise PredicateError("baseline is not numeric")
    return base, tolerance


@predicate("below_baseline", 2)
def below_baseline(signal: Any, baseline: Any) -> Any:
    value = as_number(signal)
    base, tolerance = _baseline(baseline)
    if value is None:
        raise PredicateError("signal is not numeric")
    return ok() if value < base - tolerance else fail(f"{value} is not below {base} - {tolerance}")


@predicate("above_budget_for", 3)
def above_budget_for(signal: Any, budget: Any, period: Any) -> Any:
    series = to_py(signal)
    if not isinstance(series, list) or not series:
        raise PredicateError("signal is not a series of {at, value}")
    limits = [as_number(r.get("max_cost_usd")) for r in rows(budget)]
    limit = max((x for x in limits if x is not None), default=None)
    if limit is None:
        raise PredicateError(f"{name_of(budget)} has no numeric max_cost_usd")
    span_value = to_py(period)
    window = span_value if isinstance(span_value, timedelta) else durations.parse(text(span_value))
    since = current().now - window
    points = [p for p in series if isinstance(p, Mapping) and _time(p.get("at")) >= since]
    if points and all((as_number(p.get("value")) or 0) > limit for p in points):
        return ok()
    return fail(f"cost is not above {limit} for the whole {span_value}")


@predicate("kpi_below_target_for", 3)
def kpi_below_target_for(kpis: Any, values: Any, reviews: Any) -> Any:
    count = int(as_number(reviews) or 0)
    history = to_py(values)
    if not isinstance(history, dict):
        raise PredicateError("KPI values must map each KPI to its review values")
    for row in rows(kpis):
        target = as_number(row.get("target"))
        recent = [as_number(v) for v in (history.get(text(row.get("kpi"))) or [])][-count:]
        if (
            target is not None
            and len(recent) == count
            and all(v is not None and v < target for v in recent)
        ):
            return ok()
    return fail(f"no KPI below target for {count} reviews")


@predicate("all_monitors_reporting", 0)
def all_monitors_reporting() -> Any:
    answer = current().fetch("telemetry")
    if not isinstance(answer, Evidence) or not isinstance(answer.value, dict):
        raise PredicateError("evidence not available: telemetry")
    monitors = answer.value.get("monitors")
    if not isinstance(monitors, dict) or not monitors:
        return fail("telemetry reports no monitors")
    silent = sorted(name for name, reporting in monitors.items() if not is_truthy(reporting))
    return ok() if not silent else fail(f"monitors not reporting: {', '.join(silent)}")


@predicate("regression_within_baseline", 2)
def regression_within_baseline(report: Any, baseline: Any) -> Any:
    if is_empty(baseline):
        return fail("baseline is not available")
    for i, row in enumerate(rows(report), start=1):
        if text(row.get("status")).lower() in BAD:
            return fail(
                f"{name_of(report)} row {i}: {row.get('metric')} status is {row.get('status')!r}"
            )
    return ok()


@predicate("repeated_sev1", 1)
def repeated_sev1(log: Any) -> Any:
    count = sum(1 for r in rows(log) if text(r.get("severity")).lower() == "sev1")
    return ok() if count > 1 else fail(f"{name_of(log)}: {count} sev1 incident(s)")
