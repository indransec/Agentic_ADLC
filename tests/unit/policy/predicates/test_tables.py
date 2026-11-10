"""T019: table predicates; inputs are never changed (FR-005)."""

import copy
from typing import Any

import pytest

from tests.unit.policy.conftest import Check, fails, passes

KPIS = [
    {"kpi": "handle time", "baseline": "12", "target": 8},
    {"kpi": "csat", "baseline": 3.9, "target": "4.5"},
]
T: dict[str, Any] = {
    "T1": {
        "kpis": KPIS,
        "bad": [{"kpi": "x", "baseline": "n/a", "target": 1}],
        "empty": [],
        "levels": [{"action": "a", "autonomy_level": 2}, {"action": "b", "autonomy_level": "3"}],
        "flags": [{"ok": True}, {"ok": "yes"}],
        "results": [{"result": "pass"}, {"result": "pass"}],
        "log": [{"severity": "sev1", "closed": "2026-11-01"}, {"severity": "sev3", "closed": ""}],
    }
}


def test_all_rows_in(check: Check) -> None:
    passes(check('all_rows_in(T1.kpis, "kpi", ["handle time", "csat"])', T))
    fails(check('all_rows_in(T1.kpis, "kpi", ["csat"])', T), "T1.kpis row 1: kpi is 'handle time'")


def test_all_rows_have(check: Check) -> None:
    passes(check('all_rows_have(T1.kpis, ["kpi", "baseline"])', T))
    fails(check('all_rows_have(T1.kpis, ["owner"])', T), "T1.kpis row 1: owner is empty")


def test_all_rows_numeric(check: Check) -> None:
    passes(check('all_rows_numeric(T1.kpis, ["baseline", "target"])', T))
    fails(
        check('all_rows_numeric(T1.bad, ["baseline"])', T),
        "T1.bad row 1: baseline is not numeric ('n/a')",
    )


def test_all_rows_true_and_match(check: Check) -> None:
    passes(check('all_rows_true(T1.flags, "ok")', T))
    fails(check('all_rows_true(T1.results, "ok")', T), "T1.results row 1: ok is not true")
    passes(check('all_rows_match(T1.results, "result", "pass")', T))
    fails(
        check('all_rows_match(T1.kpis, "kpi", "csat")', T),
        "T1.kpis row 1: kpi is 'handle time', not 'csat'",
    )


@pytest.mark.parametrize("name", ["all_rows_have", "all_rows_numeric"])
def test_every_row_checks_fail_on_empty_tables(check: Check, name: str) -> None:
    fails(check(f'{name}(T1.empty, ["a"])', T), "T1.empty is empty")


def test_columns(check: Check) -> None:
    passes(check('column_max(T1.levels, "autonomy_level") <= 3', T))
    fails(check('column_max(T1.levels, "autonomy_level") <= 2', T), "rule is false")
    passes(check('column_min(T1.levels, "autonomy_level") == 2.0', T))
    passes(check('column_mean(T1.kpis, "target") == 6.25', T))
    fails(check('column_mean(T1.empty, "x") > 0', T), "T1.empty is empty")
    fails(check('column_min(T1.bad, "baseline") > 0', T), "T1.bad row 1: baseline is not numeric")


def test_no_open_rows(check: Check) -> None:
    passes(check('no_open_rows(T1.log, "severity", ["sev1", "sev2"])', T))
    fails(
        check('no_open_rows(T1.log, "severity", ["sev3"])', T),
        "T1.log row 2: open with severity 'sev3'",
    )


def test_required_artifacts(check: Check, registry: Any) -> None:
    spec = registry.entry("T0").spec
    full = {a: [{c: f"{c} value" for c in cols}] for a, cols in _artifacts(spec)}
    passes(
        check(
            "all_required_artifacts_present()",
            {"T0": full, "run": {"mode": "evolve"}},
            terminal="T0",
            spec=spec,
        )
    )
    first = next(iter(full))
    fails(
        check(
            "all_required_artifacts_present()",
            {"T0": {**full, first: []}},
            terminal="T0",
            spec=spec,
        ),
        f"T0.{first} is missing or empty",
    )


def test_conditional_artifacts_follow_their_condition(check: Check, registry: Any) -> None:
    spec = registry.entry("T9").spec
    mandatory = {
        a: [{c: "v" for c in cols}]
        for a, cols, cond in _artifacts(spec, conditions=True)
        if cond is None
    }
    passes(
        check(
            "all_required_artifacts_present()",
            {"T9": mandatory, "run": {"mode": "evolve"}},
            terminal="T9",
            spec=spec,
        )
    )
    fails(
        check(
            "all_required_artifacts_present()",
            {"T9": mandatory, "run": {"mode": "retire"}},
            terminal="T9",
            spec=spec,
        ),
        "is missing or empty",
    )


def test_inputs_are_unchanged(check: Check) -> None:
    before = copy.deepcopy(T)
    for expr in (
        'all_rows_numeric(T1.kpis, ["baseline"])',
        'column_max(T1.levels, "autonomy_level") > 0',
        'no_open_rows(T1.log, "severity", ["sev1"])',
    ):
        check(expr, T)
    assert before == T


def _artifacts(spec: Any, conditions: bool = False) -> list[Any]:
    from adlc.orchestration import spec_view

    return [
        (a.id, a.columns, a.condition) if conditions else (a.id, a.columns)
        for a in spec_view.artifacts(spec)
    ]
