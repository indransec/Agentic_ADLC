"""D-9: a clarification is asked, answered, and the same run resumes; not rework (SC-002)."""

from adlc.orchestration.interfaces import Clarification
from adlc.orchestration.stubs import StubAgent
from tests.support.lifecycle import walk_to
from tests.support.orchestration import harness, person
from tests.support.pg import PlatformDatabase


def test_d9(orch_template: PlatformDatabase) -> None:
    ask = Clarification(("Is PII in scope for the claims notes?",))
    with harness(orch_template, agent=StubAgent({"T2": {1: ask}})) as h:
        usecase, run_id = walk_to(h, "T2")
        assert h.run(run_id).state == "awaiting_clarification"
        h.service.answer_clarification(
            person("engineering_lead"), f"{run_id}/clar-1", ["yes, masked"]
        )
        h.drain()
        run = h.run(run_id)
        assert run.state == "awaiting_sign_off"
        assert run.rework_count == 0
        assert [r.run_id for r in h.runs(usecase) if r.terminal_id == "T2"] == [run_id]
