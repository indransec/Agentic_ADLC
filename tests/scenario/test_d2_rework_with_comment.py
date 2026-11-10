"""D-2: a T1 rejection with a comment; T1 run 2 is built using that comment (SC-002)."""

from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person


def test_d2(h: Harness) -> None:
    usecase, run1 = walk_to(h, "T1")
    comment = "KPI baseline for claim handling time is missing"
    h.service.decide(
        person("product_owner"),
        run1,
        "rework",
        comment=comment,
        root_cause="requirement",
        reason="gap",
    )
    h.drain()
    run2 = h.active(usecase, "T1")
    assert run2.run_id == f"{usecase}/T1/run-2"
    assert run2.state == "awaiting_sign_off"
    build = [c for c in h.agent.contexts if c.run_id == run2.run_id][-1]
    assert build.trigger["comment"] == comment
    assert build.previous_artifacts.keys() == h.run(run1).artifacts.keys()
    h.pass_run(run2.run_id)
    assert h.active(usecase, "T2").state == "awaiting_sign_off"
