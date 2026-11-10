"""T040: the orchestrator runs the real engine end to end (US5; SC-002, SC-007)."""

from adlc.orchestration.stubs import StubAgent
from adlc.policy.engine import CelPolicyEngine
from tests.support.lifecycle import ORDER
from tests.support.orchestration import Harness, harness
from tests.support.pg import PlatformDatabase


def test_real_engine_passes_t0_to_t8(h: Harness) -> None:
    assert isinstance(h.policy, CelPolicyEngine)
    usecase = h.submit()
    for terminal in ORDER:
        run = h.active(usecase, terminal)
        assert run.state == "awaiting_sign_off", (terminal, run.control_results)
        assert all("synthetic" in c for c in run.control_results)
        h.pass_run(run.run_id, {"risk_tier": "medium"})
    assert h.sql("SELECT count(*) FROM run.policy_decision WHERE synthetic")[0][0] > 0


def test_bad_artifact_retries_then_escalates(orch_template: PlatformDatabase) -> None:
    bad = {"kpis": {"baseline": "n/a"}}
    with harness(orch_template, agent=StubAgent({"T1": {n: bad for n in range(1, 5)}})) as h:
        usecase = h.submit()
        h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
        run = h.active(usecase, "T1")
        assert (run.state, run.escalation_trigger) == ("escalated", "retry_limit")
        assert h.agent.calls["T1"] == 4
        reasons = [c["reason"] for c in run.control_results if not c["passed"]]
        assert reasons == ["T1.kpis row 1: baseline is not numeric ('n/a')"]


def test_agent_actor_id_is_run_scoped(h: Harness) -> None:
    """FR-016 (T055): the recorded agent id is the one authorize accepts for that run only."""
    from adlc.orchestration.interfaces import EvalContext

    usecase = h.submit()
    run_id = h.active(usecase, "T0").run_id
    actors = {
        r[0]
        for r in h.sql(
            "SELECT actor_id FROM run.run_transition WHERE run_id = :r AND actor_type IN ('agent', 'reviewer')",
            r=run_id,
        )
    }
    assert actors == {f"agent:{run_id}", f"reviewer:{run_id}"}
    ctx = EvalContext("T0", "authorize", run_id, usecase)
    assert h.policy.authorize(f"agent:{run_id}", "write", "T0.artifacts", ctx)
    other = EvalContext("T0", "authorize", f"{usecase}/T0/run-2", usecase)
    assert not h.policy.authorize(f"agent:{run_id}", "write", "T0.artifacts", other)
