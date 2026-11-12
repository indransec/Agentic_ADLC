"""011 T017 (US2; FR-006 to FR-008, FR-012; SC-003, SC-004): the T4 evaluation agent runs the
regression and golden datasets on the candidate in test, copies the harness's catalogue metrics,
imports the per-case table and records the regression pack; a weaker candidate fails a threshold
and is reworked to T3 by root cause."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import text

from tests.support.acting import acting, tool
from tests.support.fake_pilot import TEAMS, FakePilot
from tests.support.orchestration import Harness, person
from tests.support.pg import PlatformDatabase

AGENT = "t4-evaluation-agent"
CANDIDATE = "sha256:" + "5a" * 32  # the synthetic T3 candidate package
REQS = {team: f"FR-0{i}" for i, team in enumerate(TEAMS, start=1)}


def outputs(messages: Sequence[Mapping[str, str]], name: str) -> list[dict[str, Any]]:
    marker = f'<data source="tool:{name}">'
    found = []
    for message in messages:
        content = message["content"]
        if message["role"] == "user" and marker in content:
            found.append(
                json.loads(content[content.index(marker) + len(marker) : content.rindex("</data>")])
            )
    return found


class Evaluation:
    """Scripted T4 answers; keeps the harness results so a retry (a new conversation) can answer
    from them as an agent would from its notes."""

    def __init__(self) -> None:
        self.runs: list[dict[str, Any]] = []

    def answer(self, messages: Sequence[Mapping[str, str]]) -> str:
        self.runs = outputs(messages, "harness_run") or self.runs
        regression = next(r for r in self.runs if r["dataset"]["id"] == "regression")
        golden = next(r for r in self.runs if r["dataset"]["id"] == "golden")
        metrics = golden["catalogue"]
        artifacts = {
            "golden_dataset_register": [
                {
                    "dataset_id": r["dataset"]["id"],
                    "version": r["dataset"]["version"],
                    "size_count": r["dataset"]["size"],
                    "synthetic_pct": 100,
                    "real_pct": 0,
                    "approver": None,
                }
                for r in self.runs
            ],
            "test_case_results": {
                "import": {
                    "result": regression["result_id"],
                    "req_id_by": {"field": "team", "map": REQS, "default": "FR-01"},
                }
            },
            "quality_vs_threshold": [
                {
                    "metric": "task_success_rate",
                    "threshold": 0.9,
                    "actual": metrics["task_success_rate"],
                    "result": "pass" if metrics["task_success_rate"] >= 0.9 else "fail",
                }
            ],
            "rai_vs_threshold": [
                {
                    "metric": "toxicity_rate",
                    "slice": "all",
                    "threshold": 0.01,
                    "actual": metrics["toxicity_rate"],
                    "result": "pass",
                }
            ],
            "cost_latency": [
                {
                    "measure": "cost_per_task_usd",
                    "budget": 0.04,
                    "actual": metrics["cost_per_task_usd"],
                    "result": "pass",
                },
                {
                    "measure": "p95_latency_ms",
                    "budget": 2000,
                    "actual": metrics["p95_latency_ms"],
                    "result": "pass",
                },
            ],
            "failure_mode_results": [
                {
                    "scenario_id": "F-1",
                    "scenario": "unknown service",
                    "observed": "first line with review",
                    "safe_fail": True,
                }
            ],
            "defect_log": [
                {
                    "defect_id": "none",
                    "severity": "none",
                    "root_cause_terminal": None,
                    "status": "closed",
                }
            ],
            "judge_calibration": [
                {"judge": j, **v} for j, v in golden["calibration"].items() if j != "labels"
            ],
            "regression_pack": [
                {
                    "pack_id": regression["dataset"]["id"],
                    "version": regression["dataset"]["version"],
                    "case_count": regression["dataset"]["size"],
                }
            ],
        }
        for row in artifacts["judge_calibration"]:
            row.pop("labels", None)
        return json.dumps({"artifacts": artifacts})


def script(evaluation: Evaluation, retries: int = 0) -> list[Any]:
    first = [
        tool("pilot_env_create"),
        tool("dataset_registry_list"),
        tool("harness_run", {"dataset_id": "regression"}),
        tool("harness_run", {"dataset_id": "golden"}),
        evaluation.answer,
    ]
    return first + [evaluation.answer] * retries


def to_t4(h: Harness) -> tuple[str, Any]:
    for row in h.agent.base["T1"]["eval_thresholds"][
        :1
    ]:  # thresholds named as in the metric catalogue
        row.update({"metric": "task_success_rate", "operator": ">=", "threshold": 0.9})
    h.agent.base["T1"]["eval_thresholds"] = h.agent.base["T1"]["eval_thresholds"][:1]
    h.agent.base["T1"]["rai_thresholds"] = [
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
    fake = FakePilot()
    fake.packages[CANDIDATE] = {"package_hash": CANDIDATE, "template_id": "fake", "files": {}}
    return fake


def test_t4_evaluates_the_candidate_from_harness_evidence(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    evaluation = Evaluation()
    with acting(orch_template, {AGENT: script(evaluation)}, (AGENT,), tmp_path, pilot()) as a:
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
        orch_template, {AGENT: script(evaluation, retries=3)}, (AGENT,), tmp_path, fake
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
