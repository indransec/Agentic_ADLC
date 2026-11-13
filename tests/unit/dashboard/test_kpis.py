"""013 T012 (US3; FR-004; research R-05; analysis A4): every SA §12.3 KPI on fixed records."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from adlc.dashboard.kpis import (
    KPI_IDS,
    ArtifactVersion,
    ControlDecision,
    Records,
    Round,
    RunFact,
    SignOff,
    compute,
)
from adlc.dashboard.timesplit import Transition

T0 = datetime(2026, 11, 13, 9, tzinfo=UTC)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def run(
    terminal: str, n: int, status: str | None, opened: float, closed: float | None, **kw: object
) -> RunFact:
    return RunFact(
        run_id=f"UC-1/{terminal}/run-{n}",
        terminal_id=terminal,
        run_number=n,
        final_status=status,
        opened_at=at(opened),
        closed_at=None if closed is None else at(closed),
        recommendation=kw.get("recommendation"),  # type: ignore[arg-type]
        expected_seconds=kw.get("expected"),  # type: ignore[arg-type]
        blocking_controls=tuple(kw.get("blocking", ())),  # type: ignore[arg-type]
    )


RECORDS = Records(
    submitted_at=at(0),
    closed_at=None,
    now=at(600),
    runs=(
        run("T0", 1, "pass", 0, 60, recommendation="pass", expected=3600, blocking=("CTL-T0-01",)),
        run(
            "T1",
            1,
            "rework",
            60,
            120,
            recommendation="pass",
            expected=3600,
            blocking=("CTL-T1-01", "CTL-T1-02"),
        ),
        run("T1", 2, "pass", 120, 300, recommendation="pass", expected=3600),
        run("T2", 1, None, 300, None, recommendation="escalate", expected=3600),
    ),
    transitions={
        "UC-1/T0/run-1": (
            Transition("building", at(0)),
            Transition("reviewing", at(10)),
            Transition("awaiting_sign_off", at(20)),
            Transition("closed", at(60)),
        ),
        "UC-1/T2/run-1": (Transition("building", at(300)), Transition("escalated", at(400))),
    },
    sign_offs=(
        SignOff("UC-1/T0/run-1", "pass", None),
        SignOff("UC-1/T1/run-1", "rework", "requirement"),
        SignOff("UC-1/T1/run-2", "pass", None),
        SignOff("UC-1/T2/run-1", "terminate", None),  # recommended escalate: not counted (A4)
    ),
    rounds=(
        Round("UC-1/T1/run-2", "product_owner", at(130), at(150)),
        Round("UC-1/T1/run-2", "business_owner", at(160), None),  # unanswered
    ),
    escalations=(("UC-1/T2/run-1", "retry_limit"),),
    artifact_versions=(
        ArtifactVersion("UC-1/T0/run-1", "card", 1, "agent"),
        ArtifactVersion("UC-1/T1/run-1", "reqs", 1, "agent"),
        ArtifactVersion("UC-1/T1/run-1", "reqs", 2, "person"),
        ArtifactVersion("UC-1/T1/run-2", "reqs", 1, "agent"),
    ),
    control_decisions=(
        ControlDecision("UC-1/T0/run-1", "CTL-T0-01", 1, True),
        ControlDecision("UC-1/T1/run-1", "CTL-T1-01", 1, False),
        ControlDecision("UC-1/T1/run-1", "CTL-T1-01", 2, True),  # a later attempt: not first-time
        ControlDecision("UC-1/T1/run-1", "CTL-T1-02", 1, True),
        ControlDecision("UC-1/T1/run-1", "CTL-T1-09", 1, False),  # advisory: not counted
    ),
)


def kpis() -> dict[str, dict[str, Any]]:
    return {k["id"]: k for k in compute(RECORDS)}


def test_all_eleven_with_definitions() -> None:
    found = kpis()
    assert tuple(found) == KPI_IDS and len(KPI_IDS) == 11
    assert all(k["name"] and k["definition"] for k in found.values())


def test_elapsed_and_time_split() -> None:
    found = kpis()
    assert found["elapsed"]["value"] == 600 * 60
    split = found["time_split"]["per_terminal"]
    assert (
        split["T0"]["agent"] == 600
        and split["T0"]["reviewer"] == 600
        and split["T0"]["people"] == 2400
    )
    assert split["T2"]["people"] == 200 * 60  # escalated until now


def test_reworks_clarifications_and_waits() -> None:
    found = kpis()
    assert found["reworks"]["value"] == 1 and found["reworks"]["per_terminal"] == {
        "T1": {"requirement": 1}
    }
    assert found["clarifications"]["value"] == 2
    assert found["clarifications"]["per_terminal"] == {
        "T1": {"product_owner": 1, "business_owner": 1}
    }
    assert found["clarification_wait"]["value"] == 20 * 60  # answered rounds only
    assert found["clarification_wait"]["per_terminal"] == {"T1": 1200.0}


def test_rates() -> None:
    found = kpis()
    assert found["first_pass_yield"]["value"] == pytest.approx(1 / 2)  # T0 yes, T1 no; T2 open
    assert found["escalations"]["value"] == 1
    assert found["escalations"]["detail"] == [
        {"run_id": "UC-1/T2/run-1", "terminal_id": "T2", "trigger": "retry_limit"}
    ]
    assert found["reviewer_agreement"]["value"] == pytest.approx(2 / 3)  # escalate ignored
    assert found["human_edit_rate"]["value"] == pytest.approx(1 / 3)
    assert found["control_first_pass"]["value"] == pytest.approx(2 / 3)
    assert found["sla_adherence"]["value"] == pytest.approx(2 / 3)  # T1 run-2 took 3 h > 1 h


def test_no_data_is_null_never_zero() -> None:
    empty = Records(at(0), None, at(1), (), {}, (), (), (), (), ())
    found = {k["id"]: k for k in compute(empty)}
    for kpi in (
        "clarification_wait",
        "first_pass_yield",
        "reviewer_agreement",
        "human_edit_rate",
        "control_first_pass",
        "sla_adherence",
    ):
        assert found[kpi]["value"] is None, kpi
    assert found["reworks"]["value"] == 0  # a count of nothing is zero
