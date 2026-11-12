"""011 T017 (US2; FR-006 to FR-008, FR-012; SC-003, SC-004): the T4 evaluation agent runs the
regression and golden datasets on the candidate in test, copies the harness's catalogue metrics,
imports the per-case table and records the regression pack; a weaker candidate fails a threshold
and is reworked to T3 by root cause."""

from pathlib import Path
from typing import Any

from sqlalchemy import text

from tests.support.acting import acting
from tests.support.acting_scripts import REQS, Evaluation
from tests.support.fake_pilot import FakePilot, with_candidate
from tests.support.orchestration import Harness, person
from tests.support.pg import PlatformDatabase

AGENT = "t4-evaluation-agent"
CANDIDATE = "sha256:" + "5a" * 32  # the synthetic T3 candidate package


def to_t4(h: Harness) -> tuple[str, Any]:
    t1: dict[str, Any] = h.agent.base["T1"]  # type: ignore[assignment]
    # thresholds named as in the metric catalogue
    t1["eval_thresholds"] = [
        {
            "metric": "task_success_rate",
            "operator": ">=",
            "threshold": 0.9,
            "dataset_scope": "golden",
        }
    ]
    t1["rai_thresholds"] = [
        {"metric": "toxicity_rate", "operator": "<=", "threshold": 0.01, "slice": "all"}
    ]
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "low"})
    for terminal in ("T1", "T2", "T3"):
        h.pass_run(h.active(usecase, terminal).run_id)
    return usecase, h.active(usecase, "T4")


def decisions(h: Harness, run_id: str) -> dict[str, tuple[bool, bool]]:
    with h.app.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT check_id, passed, synthetic FROM run.policy_decision WHERE run_id = :r AND check_id LIKE 'CTL-T4-%' ORDER BY policy_decision_id"
            ),
            {"r": run_id},
        ).all()
    return {str(c): (bool(p), bool(s)) for c, p, s in rows}


def pilot() -> FakePilot:
    return with_candidate(FakePilot())


def test_t4_evaluates_the_candidate_from_harness_evidence(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    evaluation = Evaluation()
    with acting(orch_template, {AGENT: evaluation.script()}, (AGENT,), tmp_path, pilot()) as a:
        usecase, run = to_t4(a.h)
        assert run.state == "awaiting_sign_off", [c for c in run.control_results if not c["passed"]]
        assert a.pilot.hosts["test"].running["package_hash"] == CANDIDATE  # type: ignore[index]
        assert len(run.artifacts["test_case_results"]) == 120  # imported from the regression result
        assert {r["req_id"] for r in run.artifacts["test_case_results"]} == set(REQS.values())
        found = decisions(a.h, run.run_id)
        for check in ("CTL-T4-01", "CTL-T4-11", "CTL-T4-12", "CTL-T4-13", "CTL-T4-14"):
            assert found[check][0], check
        assert found["CTL-T4-11"][1] is False  # read from the recorded harness result
        with a.h.app.connect() as conn:
            detail = conn.execute(
                text(
                    "SELECT detail FROM run.run_activity WHERE run_id = :r AND detail ? 'imports'"
                ),
                {"r": run.run_id},
            ).scalar_one()
        assert (
            detail["imports"][0]["artifact"] == "test_case_results"
            and detail["imports"][0]["rows"] == 120
        )


def test_a_weaker_candidate_fails_a_threshold_and_is_reworked_to_t3(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    evaluation = Evaluation()
    fake = pilot()
    fake.hosts["test"].mode = "degraded"
    with acting(
        orch_template, {AGENT: evaluation.script(retries=3)}, (AGENT,), tmp_path, fake
    ) as a:
        usecase, run = to_t4(a.h)
        a.h.drain()
        run = a.h.run(run.run_id)
        assert run.state == "escalated"  # a missed threshold is not fixable by the agent
        failed = [c for c in run.control_results if not c["passed"]]
        assert any(c["id"] == "CTL-T4-01" and "task_success_rate" in c["reason"] for c in failed), (
            failed
        )
        assert not any(
            c["id"] in ("CTL-T4-11", "CTL-T4-13", "CTL-T4-14") for c in failed
        )  # copied values match
        a.h.service.complete_escalation(person("qa_eval_lead"), run.run_id, run.artifacts)
        a.h.drain()
        a.h.service.decide(
            person("qa_eval_lead"),
            run.run_id,
            "rework",
            comment="Routing below threshold",
            root_cause="implementation",
            reason="weaker candidate",
            fields={"defect_log": "DEF-1"},
        )
        a.h.drain()
        open_runs = [r.run_id for r in a.h.runs(usecase) if r.state != "closed"]
        assert open_runs == [f"{usecase}/T3/run-2"]
