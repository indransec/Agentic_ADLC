"""T006: compile once, list references, never raise on parse errors."""

from pathlib import Path

from adlc.orchestration import spec_view
from adlc.policy.compiler import compile_rule
from adlc.spec_toolkit.loader import load_bundle

SPECS = Path(__file__).resolve().parents[3] / "adlc-specs"


def test_cached_and_references() -> None:
    first = compile_rule('all_rows_numeric(T1.kpis, ["baseline"]) && run.rework_count < param.x')
    assert (
        compile_rule('all_rows_numeric(T1.kpis, ["baseline"]) && run.rework_count < param.x')
        is first
    )
    assert first.roots == ("T1", "run", "param")
    assert ("T1", "kpis") in first.refs
    assert first.calls == ("all_rows_numeric",)


def test_macro_variables_are_not_references() -> None:
    compiled = compile_rule('T1.kpis.exists(r, r.baseline == "1")')
    assert compiled.roots == ("T1",)


def test_parse_error_is_a_value() -> None:
    compiled = compile_rule("T1.kpis &&& ")
    assert compiled.ast is None and compiled.error


def test_every_spec_rule_compiles() -> None:
    bundle = load_bundle(SPECS)
    rules = [
        check.expression
        for t in bundle.usable_terminals()
        for check in (*spec_view.prerequisites(t.data), *spec_view.controls(t.data))
    ]
    assert len(rules) == 98
    assert all(compile_rule(r).error is None for r in rules)
