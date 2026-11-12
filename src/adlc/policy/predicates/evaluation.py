"""Evaluation and assurance predicates (contracts/predicates.md)."""

import operator
from collections.abc import Callable
from typing import Any

from adlc.policy.predicates import predicate
from adlc.policy.predicates.context import PredicateError, fail, name_of, ok, rows
from adlc.policy.values import as_number, is_truthy, text, to_py

OPERATORS: dict[str, Callable[[float, float], bool]] = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "==": operator.eq,
}
FAILED = ("fail", "failed")


def _by_metric(table: Any) -> dict[str, dict[str, Any]]:
    return {text(r.get("metric")): r for r in rows(table)}


@predicate("all_metrics_meet_thresholds", 2)
def all_metrics_meet_thresholds(results: Any, thresholds: Any) -> Any:
    measured = _by_metric(results)
    for i, row in enumerate(rows(thresholds), start=1):
        metric, op = text(row.get("metric")), text(row.get("operator"))
        if op not in OPERATORS:
            raise PredicateError(f"{name_of(thresholds)} row {i}: unknown operator {op!r}")
        if metric not in measured:
            return fail(f"{name_of(results)}: no result for {metric}")
        actual, limit = as_number(measured[metric].get("actual")), as_number(row.get("threshold"))
        if actual is None or limit is None:
            return fail(f"{name_of(results)}: {metric} actual or threshold is not numeric")
        if not OPERATORS[op](actual, limit):
            return fail(f"{name_of(results)}: {metric} {actual} does not meet {op} {limit}")
    return ok()


def _critical(row: dict[str, Any]) -> bool:
    return is_truthy(row.get("critical")) or text(row.get("severity")).lower() == "critical"


@predicate("no_critical_threshold_missed", 2)
def no_critical_threshold_missed(quality: Any, rai: Any) -> Any:
    for table in (quality, rai):
        for i, row in enumerate(rows(table), start=1):
            if text(row.get("result")).lower() in FAILED and _critical(row):
                return fail(f"{name_of(table)} row {i}: critical threshold missed")
    return ok()


def _measured(table: Any, word: str) -> list[tuple[int, dict[str, Any]]]:
    return [
        (i, r) for i, r in enumerate(rows(table), start=1) if word in text(r.get("measure")).lower()
    ]


@predicate("cost_within_budget", 2)
def cost_within_budget(measured: Any, budget: Any) -> Any:
    limits = [as_number(r.get("max_cost_usd")) for r in rows(budget)]
    limit = max((x for x in limits if x is not None), default=None)
    if limit is None:
        return fail(f"{name_of(budget)} has no numeric max_cost_usd")
    for i, row in _measured(measured, "cost"):
        actual = as_number(row.get("actual"))
        if actual is None or actual > limit:
            return fail(
                f"{name_of(measured)} row {i}: cost {row.get('actual')!r} is above the budget {limit}"
            )
    return ok()


@predicate("latency_within_nfr", 2)
def latency_within_nfr(measured: Any, nfrs: Any) -> Any:
    targets = [
        as_number(r.get("target"))
        for r in rows(nfrs)
        if text(r.get("category")).lower() == "latency"
    ]
    limit = min((x for x in targets if x is not None), default=None)
    if limit is None:
        return fail(f"{name_of(nfrs)} has no numeric latency NFR")
    for i, row in _measured(measured, "latency"):
        actual = as_number(row.get("actual"))
        if actual is None or actual > limit:
            return fail(
                f"{name_of(measured)} row {i}: latency {row.get('actual')!r} is above the NFR {limit}"
            )
    return ok()


@predicate("judge_disputed", 1)
def judge_disputed(calibration: Any) -> Any:
    for row in rows(calibration):
        if is_truthy(row.get("disputed")):
            return ok()
    return fail(f"{name_of(calibration)}: no dispute recorded")


@predicate("scenario_passed", 2)
def scenario_passed(table: Any, scenario: Any) -> Any:
    wanted = text(scenario)
    for row in rows(table):
        if text(row.get("scenario")) == wanted:
            result = text(row.get("result")).lower()
            return (
                ok()
                if result == "pass"
                else fail(f"{name_of(table)}: {wanted} result is {result!r}")
            )
    return fail(f"{name_of(table)}: no {wanted} scenario")


@predicate("no_unmitigated_critical", 1)
def no_unmitigated_critical(threats: Any) -> Any:
    for i, row in enumerate(rows(threats), start=1):
        risk = text(row.get("residual_risk")).lower()
        result = text(row.get("result")).lower()
        if risk in ("critical", "high") and result not in ("mitigated", "pass"):
            return fail(f"{name_of(threats)} row {i}: {risk} risk is not mitigated ({result!r})")
    return ok()


def _disagree(table: Any) -> Any:
    decisions = {text(r.get("decision")).lower() for r in rows(table)}
    return ok() if len(decisions) > 1 else fail(f"{name_of(table)}: decisions agree")


@predicate("assurance_disagreement", 1)
def assurance_disagreement(attestation: Any) -> Any:
    return _disagree(attestation)


@predicate("unacceptable_residual_risk", 1)
def unacceptable_residual_risk(register: Any) -> Any:
    for row in rows(register):
        if text(row.get("decision")).lower() in ("unacceptable", "reject"):
            return ok()
    return fail(f"{name_of(register)}: no residual risk rated unacceptable")


# ------------------------------------------------------------------ 011: copied values checked

NOT_MEASURED = ("", "not measured", "n/a")
TOLERANCE = 0.001


def _same(copied: Any, recorded: Any) -> bool:
    if isinstance(recorded, bool):
        return is_truthy(copied) == recorded
    number = as_number(recorded)
    if number is not None:
        got = as_number(copied)
        return got is not None and abs(got - number) <= TOLERANCE
    return text(copied).strip().lower() == text(recorded).strip().lower()


def _recorded(recorded: Any) -> dict[str, Any]:
    value = to_py(recorded)
    if not isinstance(value, dict):
        raise PredicateError(f"{name_of(recorded)} is not a map of recorded results")
    return {text(k): v for k, v in value.items()}


@predicate("rows_match", 3)
def rows_match(table: Any, key_column: Any, recorded: Any) -> Any:
    """011 (FR-012): every row's key has a recorded result, and each of the row's columns that the
    result records equals it (numbers within 0.001)."""
    found, key = _recorded(recorded), text(key_column)
    for i, row in enumerate(rows(table), start=1):
        name = text(row.get(key))
        if name not in found:
            return fail(f"{name_of(table)} row {i}: no recorded result for {name}")
        values = found[name] if isinstance(found[name], dict) else {}
        for column, value in values.items():
            if column in row and not _same(row[column], value):
                return fail(
                    f"{name_of(table)} row {i}: {name} {column} {row[column]} is not the "
                    f"recorded {value}"
                )
    return ok()


@predicate("rows_match_value", 4)
def rows_match_value(table: Any, key_column: Any, column: Any, recorded: Any) -> Any:
    """011 (FR-012): each row's measured column equals the recorded value for its key; a key that
    was not measured must say so ("not measured")."""
    found, key, measured = _recorded(recorded), text(key_column), text(column)
    for i, row in enumerate(rows(table), start=1):
        name, copied = text(row.get(key)), row.get(measured)
        if name not in found:
            if text(copied).strip().lower() not in NOT_MEASURED:
                return fail(f"{name_of(table)} row {i}: {name} was not measured")
            continue
        if not _same(copied, found[name]):
            return fail(
                f"{name_of(table)} row {i}: {name} {measured} {copied} is not the recorded "
                f"{found[name]}"
            )
    return ok()
