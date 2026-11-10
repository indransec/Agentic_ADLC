"""T025: automated controls with the real engine (US2)."""

from adlc.orchestration.interfaces import EvalContext
from adlc.orchestration.stubs import StubAgent
from adlc.policy.factory import build_policy_engine
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, harness
from tests.support.pg import PlatformDatabase


def test_good_artifacts_pass_every_control(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1")
    results = h.run(t1).control_results
    assert results and all(c["passed"] for c in results)


def test_bad_cell_fails_with_table_row_and_column(orch_template: PlatformDatabase) -> None:
    bad = {"kpis": {"baseline": "n/a"}}
    with harness(orch_template, agent=StubAgent({"T1": {n: bad for n in range(1, 5)}})) as h:
        usecase, t1 = walk_to(h, "T1")
        run = h.run(t1)
        assert (run.state, run.escalation_trigger, run.auto_retries) == (
            "escalated",
            "retry_limit",
            3,
        )
        failed = {c["id"]: c["reason"] for c in run.control_results if not c["passed"]}
        assert failed == {"CTL-T1-02": "T1.kpis row 1: baseline is not numeric ('n/a')"}


def test_advisory_failure_is_recorded_only(orch_template: PlatformDatabase) -> None:
    weak = {"agentic_suitability": {"score_1_5": 1}}
    with harness(orch_template, agent=StubAgent({"T0": {1: weak}})) as h:
        usecase = h.submit()
        run = h.active(usecase, "T0")
        assert run.state == "awaiting_sign_off"
        advisory = [c for c in run.control_results if c["id"] == "CTL-T0-03"][0]
        assert (advisory["passed"], advisory["blocking"]) == (False, False)


def test_missing_external_evidence_fails_closed(h: Harness) -> None:
    usecase, t5 = walk_to(h, "T5")
    no_synthetic = build_policy_engine(h.app, SqlSpecRegistry(h.app), h.clock)
    result = no_synthetic.evaluate(
        "redteam.injection_success_rate <= param.injection_success_max",
        EvalContext("T5", "CTL-T5-01", t5, usecase),
    )
    assert (result.passed, result.reason) == (False, "evidence not available: redteam")


def test_synthetic_control_results_are_labelled(h: Harness) -> None:
    usecase, t5 = walk_to(h, "T5")
    labels = {c["id"]: c["synthetic"] for c in h.run(t5).control_results}
    assert labels["CTL-T5-01"] is True  # red-team evidence is synthetic
    assert labels["CTL-T5-07"] is False  # an artifact check reads no synthetic evidence
