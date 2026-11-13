"""T005 (012 research R-09): artifacts the platform builds from records, never an agent."""

from datetime import UTC, datetime
from typing import Any

import pytest

from adlc.orchestration.spec_view import BUILT_FORMATS, ArtifactSpec
from adlc.policy.built_artifacts import GateRecord, baseline, gate_summary, signed_record

AT = datetime(2026, 11, 12, 10, tzinfo=UTC)


def _sign_off(role: str, decision: str) -> dict[str, Any]:
    return {"role": role, "decision": decision, "person": f"p-{role}", "signed_at": AT}


def test_built_formats_are_the_three_kinds() -> None:
    assert BUILT_FORMATS == ("signed_record", "baseline", "gate_summary")
    assert ArtifactSpec("a", ("x",), None, "baseline").built
    assert not ArtifactSpec("a", ("x",), None, "table").built


def test_signed_record_lists_pass_and_exception_sign_offs() -> None:
    rows = signed_record(
        [_sign_off("owner", "pass"), _sign_off("risk", "exception"), _sign_off("x", "rework")]
    )
    assert rows == [
        {"role": "owner", "decision": "pass", "date": "2026-11-12"},
        {"role": "risk", "decision": "exception", "date": "2026-11-12"},
    ]


def test_baseline_reads_the_named_field_with_the_spec_tolerance() -> None:
    built_from = {"evidence": "harness", "field": "metrics.task_success_rate", "tolerance": 0.05}
    evidence = {"metrics": {"task_success_rate": 0.94, "toxicity_rate": 0.0}}
    assert baseline(built_from, evidence) == [
        {"metric": "task_success_rate", "value": 0.94, "tolerance": 0.05}
    ]


@pytest.mark.parametrize(
    "evidence",
    [None, {}, {"metrics": {}}, {"metrics": {"task_success_rate": "n/a"}}],
)
def test_baseline_without_a_measured_number_is_not_built(evidence: Any) -> None:
    built_from = {"evidence": "harness", "field": "metrics.task_success_rate", "tolerance": 0.05}
    assert baseline(built_from, evidence) is None  # never a default value (fails closed)


def test_gate_summary_has_a_row_per_earlier_terminal() -> None:
    records = [
        GateRecord("T0", "pass", ("alice",), AT, ()),
        GateRecord("T5", "exception", ("bob", "carol"), AT, (("WVR-0001", "2027-03-31"),)),
    ]
    assert gate_summary(records) == [
        {
            "terminal": "T0",
            "status": "pass",
            "signed_by": "alice",
            "date": "2026-11-12",
            "open_waivers": "",
            "waiver_expiry": "",
        },
        {
            "terminal": "T5",
            "status": "exception",
            "signed_by": "bob, carol",
            "date": "2026-11-12",
            "open_waivers": "WVR-0001",
            "waiver_expiry": "2027-03-31",
        },
    ]


def test_gate_summary_orders_terminals_by_number() -> None:
    records = [GateRecord(t, "pass", (), None, ()) for t in ("T10", "T2", "T1")]
    assert [r["terminal"] for r in gate_summary(records)] == ["T1", "T2", "T10"]
