"""D-3: T4 rework with root cause `implementation` opens T3, not T1 or T2 (SC-002)."""

from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person


def test_d3(h: Harness) -> None:
    usecase, t4 = walk_to(h, "T4")
    h.service.decide(
        person("qa_eval_lead"),
        t4,
        "rework",
        comment="tool timeout",
        root_cause="implementation",
        reason="eval failures",
        fields={"defect_log": "DEF-1"},
    )
    h.drain()
    open_runs = [r for r in h.runs(usecase) if r.state != "closed"]
    assert [r.run_id for r in open_runs] == [f"{usecase}/T3/run-2"]
    h.pass_run(open_runs[0].run_id)
    t4_again = h.active(usecase, "T4")
    assert t4_again.run_number == 2 and t4_again.rework_count == 0
