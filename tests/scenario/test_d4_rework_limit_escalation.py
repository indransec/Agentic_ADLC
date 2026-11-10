"""D-4: the fourth T1 rework opens run 5 escalated; the owner completes it (SC-002)."""

from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person


def test_d4(h: Harness) -> None:
    usecase, run_id = walk_to(h, "T1")
    for _ in range(4):
        h.service.decide(
            person("product_owner"),
            run_id,
            "rework",
            comment="thresholds still wrong",
            root_cause="requirement",
            reason="r",
        )
        h.drain()
        run_id = h.active(usecase, "T1").run_id
    run = h.run(run_id)
    assert (run.run_number, run.state, run.escalation_trigger) == (5, "escalated", "rework_limit")
    assert h.agent.calls["T1"] == 4  # run 5 is not built by the agent
    # The owner completes every artifact by hand (here: the synthetic set with one KPI edited);
    # the next terminal's prerequisites read them, so a partial completion would block it.
    completed = {name: [dict(r) for r in rows] for name, rows in h.agent.base["T1"].items()}
    completed["kpis"][0]["kpi"] = "claim handling minutes (by hand)"
    h.service.complete_escalation(person("product_owner"), run_id, completed)
    h.pass_run(run_id)
    assert h.active(usecase, "T2").state == "awaiting_sign_off"
