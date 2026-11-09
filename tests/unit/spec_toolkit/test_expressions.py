"""T031: CEL parsing and reference extraction (research R-01, R-02)."""

import pytest

from adlc.spec_toolkit.expressions import ExpressionError, parse_expression


def test_member_chains_and_calls() -> None:
    parsed = parse_expression(
        'T0.status in ["pass", "exception"] && all_rows_have(T1.kpis, ["baseline"]) '
        "&& run.age > param.x && size(intake.free_text) >= 200"
    )
    assert {r.path for r in parsed.refs} == {
        ("T0", "status"),
        ("T1", "kpis"),
        ("run", "age"),
        ("param", "x"),
        ("intake", "free_text"),
    }
    calls = {c.name: c for c in parsed.calls}
    assert set(calls) == {"all_rows_have", "size"}
    args = calls["all_rows_have"].args
    assert [a.kind for a in args] == ["ref", "list"]
    assert args[0].ref is not None and args[0].ref.path == ("T1", "kpis")
    assert args[1].items == ("baseline",)


def test_literal_argument_kinds() -> None:
    call = parse_expression('f(a.b, "s", 3, 1.5, ["x", "y"], true)').calls[0]
    assert [a.kind for a in call.args] == ["ref", "string", "number", "number", "list", "other"]


def test_macro_variables_are_local() -> None:
    parsed = parse_expression("T1.rows.exists(r, r.ok) && T1.rows.all(x, x.size > 0)")
    assert {r.path for r in parsed.refs} == {("T1", "rows")}
    assert {m for m in parsed.methods} == {"exists", "all"}


def test_bare_identifier_is_a_reference() -> None:
    assert [r.path for r in parse_expression("enabled").refs] == [("enabled",)]


def test_nullary_call() -> None:
    parsed = parse_expression("all_required_artifacts_present()")
    assert parsed.calls[0].name == "all_required_artifacts_present"
    assert parsed.calls[0].args == ()


@pytest.mark.parametrize("bad", ["bad syntax ((", "a &&", ""])
def test_parse_errors(bad: str) -> None:
    with pytest.raises(ExpressionError):
        parse_expression(bad)
