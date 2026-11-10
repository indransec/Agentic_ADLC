"""T007: evaluate never raises; any non-true outcome fails with a reason (FR-003, FR-004)."""

from collections.abc import Iterator
from typing import Any

from celpy import celtypes
from hypothesis import given, settings
from hypothesis import strategies as st

from adlc.orchestration.interfaces import EvalContext
from adlc.policy.engine import CelPolicyEngine
from adlc.policy.evidence import InMemoryEvidenceProvider
from adlc.policy.predicates.context import fail
from adlc.policy.store import MemorySink

CTX = EvalContext("T1", "CTL-X", "UC-0001/T1/run-1", "UC-0001")


def _engine(
    sources: dict[str, Any], predicates: dict[str, Any] | None = None, timer: Any = None
) -> tuple[CelPolicyEngine, MemorySink]:
    sink = MemorySink()
    kwargs: dict[str, Any] = {"sink": sink}
    if timer is not None:
        kwargs["timer"] = timer
    return CelPolicyEngine(InMemoryEvidenceProvider(sources), predicates or {}, **kwargs), sink


SOURCES = {
    "T0": {"status": "pass", "risk_classification": [{"tier": "low"}], "empty": []},
    "run": {"mode": "evolve"},
}


def _reason(expression: str, sources: dict[str, Any] = SOURCES, **kw: Any) -> str:
    engine, _ = _engine(sources, **kw)
    result = engine.evaluate(expression, CTX)
    assert result.passed is False
    return result.reason


def test_true_passes() -> None:
    engine, sink = _engine(SOURCES)
    result = engine.evaluate('T0.status in ["pass", "exception"]', CTX)
    assert (result.passed, result.reason) == (True, "passed")
    assert len(sink.decisions) == 1


def test_missing_source() -> None:
    assert _reason("ci.status == 'green'") == "evidence not available: ci"


def test_missing_member_of_available_source() -> None:
    assert _reason("T0.value_hypothesis != null") == "evidence not available: T0.value_hypothesis"
    assert (
        _reason("T0.risk_classification.rating == 'x'")
        == "evidence not available: T0.risk_classification.rating"
    )


def test_table_column_reads_first_row() -> None:
    engine, _ = _engine(SOURCES)
    assert engine.evaluate("T0.risk_classification.tier == 'low'", CTX).passed


def test_unneeded_missing_evidence_is_absorbed() -> None:
    engine, _ = _engine(SOURCES)
    assert engine.evaluate('run.mode != "retire" || retirement.done', CTX).passed
    assert (
        _reason('run.mode == "retire" || retirement.done') == "evidence not available: retirement"
    )


def test_false_rule() -> None:
    assert _reason("T0.status == 'rework'") == "rule is false: T0.status == 'rework'"


def test_predicate_reason_wins() -> None:
    def check(table: Any) -> Any:
        return fail(f"{table.ref} row 1: no")

    assert (
        _reason("check(T0.risk_classification)", predicates={"check": (check, 1)})
        == "T0.risk_classification row 1: no"
    )


def test_not_a_bool() -> None:
    assert _reason("T0.status").startswith("rule did not return true/false")


def test_evaluation_error_and_unknown_function() -> None:
    assert _reason("1 / 0 == 1").startswith("evaluation error")
    assert _reason("no_such_predicate(T0.status)").startswith("evaluation error")
    assert _reason("T0.status &&&").startswith("evaluation error")


def test_too_slow() -> None:
    ticks: Iterator[float] = iter([0.0, 2.0])
    assert _reason("T0.status == 'pass'", timer=lambda: next(ticks)).startswith(
        "evaluation too slow"
    )


def test_too_large() -> None:
    big = {"T0": {"rows": [{"a": 1}] * 10_001, "text": "x" * 100_001}}
    assert _reason("size(T0.rows) > 0", sources=big) == "evidence too large: T0.rows"


def test_predicate_exception_fails_closed() -> None:
    def broken(x: Any) -> Any:
        raise RuntimeError("boom")

    assert _reason("broken(T0.status)", predicates={"broken": (broken, 1)}).startswith(
        "evaluation error"
    )


def test_decision_records_inputs_without_copying_tables() -> None:
    engine, sink = _engine(SOURCES)
    engine.evaluate("size(T0.risk_classification) == 1", CTX)
    read = sink.decisions[0].inputs
    assert read["T0.risk_classification"]["value"]["rows"] == 1
    assert "content_hash" in read["T0.risk_classification"]["value"]


@settings(max_examples=300, deadline=None)
@given(st.text(max_size=60))
def test_never_raises(expression: str) -> None:
    engine, _ = _engine(SOURCES)
    result = engine.evaluate(expression, CTX)
    assert isinstance(result.passed, bool) and result.reason


def test_bool_type_is_bool() -> None:
    assert isinstance(celtypes.BoolType(True), celtypes.BoolType)
