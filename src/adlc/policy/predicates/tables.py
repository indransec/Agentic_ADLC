"""Row and column checks over artifact tables (contracts/predicates.md)."""

from statistics import mean
from typing import Any

from celpy import celtypes

from adlc.orchestration import spec_view
from adlc.policy.predicates import predicate
from adlc.policy.predicates.context import PredicateError, current, fail, name_of, ok, rows, strings
from adlc.policy.values import as_number, is_empty, is_open_row, is_truthy, text


def _rows(table: Any) -> list[dict[str, Any]] | None:
    found = rows(table)
    return found if found else None


def _empty(table: Any) -> Any:
    return fail(f"{name_of(table)} is empty")


@predicate("all_rows_in", 3)
def all_rows_in(table: Any, column: Any, allowed: Any) -> Any:
    found = _rows(table)
    if found is None:
        return _empty(table)
    col, permitted = text(column), strings(allowed)
    for i, row in enumerate(found, start=1):
        if text(row.get(col)) not in permitted:
            return fail(
                f"{name_of(table)} row {i}: {col} is {row.get(col)!r}, not one of {permitted}"
            )
    return ok()


@predicate("all_rows_have", 2)
def all_rows_have(table: Any, columns: Any) -> Any:
    found = _rows(table)
    if found is None:
        return _empty(table)
    for i, row in enumerate(found, start=1):
        for col in strings(columns):
            if is_empty(row.get(col)):
                return fail(f"{name_of(table)} row {i}: {col} is empty")
    return ok()


@predicate("all_rows_numeric", 2)
def all_rows_numeric(table: Any, columns: Any) -> Any:
    found = _rows(table)
    if found is None:
        return _empty(table)
    for i, row in enumerate(found, start=1):
        for col in strings(columns):
            if as_number(row.get(col)) is None:
                return fail(f"{name_of(table)} row {i}: {col} is not numeric ({row.get(col)!r})")
    return ok()


@predicate("all_rows_true", 2)
def all_rows_true(table: Any, column: Any) -> Any:
    found = _rows(table)
    if found is None:
        return _empty(table)
    col = text(column)
    for i, row in enumerate(found, start=1):
        if not is_truthy(row.get(col)):
            return fail(f"{name_of(table)} row {i}: {col} is not true ({row.get(col)!r})")
    return ok()


@predicate("all_rows_match", 3)
def all_rows_match(table: Any, column: Any, value: Any) -> Any:
    found = _rows(table)
    if found is None:
        return _empty(table)
    col, wanted = text(column), text(value)
    for i, row in enumerate(found, start=1):
        if text(row.get(col)) != wanted:
            return fail(f"{name_of(table)} row {i}: {col} is {row.get(col)!r}, not {wanted!r}")
    return ok()


def _numbers(table: Any, column: Any) -> list[float]:
    found = rows(table)
    col = text(column)
    if not found:
        raise PredicateError(f"{name_of(table)} is empty")
    out = []
    for i, row in enumerate(found, start=1):
        number = as_number(row.get(col))
        if number is None:
            raise PredicateError(
                f"{name_of(table)} row {i}: {col} is not numeric ({row.get(col)!r})"
            )
        out.append(number)
    return out


@predicate("column_mean", 2)
def column_mean(table: Any, column: Any) -> Any:
    return celtypes.DoubleType(mean(_numbers(table, column)))


@predicate("column_min", 2)
def column_min(table: Any, column: Any) -> Any:
    return celtypes.DoubleType(min(_numbers(table, column)))


@predicate("column_max", 2)
def column_max(table: Any, column: Any) -> Any:
    return celtypes.DoubleType(max(_numbers(table, column)))


@predicate("no_open_rows", 3)
def no_open_rows(table: Any, column: Any, values: Any) -> Any:
    found = rows(table)
    col, flagged = text(column), strings(values)
    for i, row in enumerate(found, start=1):
        if is_open_row(row) and text(row.get(col)) in flagged:
            return fail(f"{name_of(table)} row {i}: open with {col} {row.get(col)!r}")
    return ok()


@predicate("all_required_artifacts_present", 0)
def all_required_artifacts_present() -> Any:
    call = current()
    spec = call.spec
    if spec is None:
        raise PredicateError("the run's spec is not available")
    terminal = call.eval.terminal_id
    answer = call.fetch(terminal)
    record = getattr(answer, "value", None)
    if not isinstance(record, dict):
        raise PredicateError(f"evidence not available: {terminal}")
    for artifact in spec_view.artifacts(spec):
        if artifact.condition is not None:
            applies = call.nested(artifact.condition, f"applies:{artifact.id}")
            if not applies.passed:
                continue
        table = record.get(artifact.id)
        if not isinstance(table, list) or not table:
            return fail(f"{terminal}.{artifact.id} is missing or empty")
        for column in artifact.columns:
            if not all(isinstance(r, dict) and column in r for r in table):
                return fail(f"{terminal}.{artifact.id}: column {column} is missing")
    return ok()
