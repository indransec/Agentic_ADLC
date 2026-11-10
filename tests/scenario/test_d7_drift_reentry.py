"""D-7: T8 drift → T9 → T9.reentry.T2 → T2 (SC-002)."""

from adlc.orchestration.service import Actor
from adlc.orchestration.stubs import StubAgent
from tests.support.lifecycle import walk_to
from tests.support.orchestration import harness
from tests.support.pg import PlatformDatabase


def test_d7(orch_template: PlatformDatabase) -> None:
    agent = StubAgent(
        {
            "T9": {
                1: {
                    "change_impact_assessment": {
                        "change_class": "moderate",
                        "reentry_terminal": "T2",
                    }
                }
            }
        }
    )
    with harness(orch_template, agent=agent) as h:
        usecase, _ = walk_to(h, "T8")
        h.service.raise_operational_event(Actor.system("monitor"), usecase, "drift", {"psi": 0.31})
        h.drain()
        t9 = h.active(usecase, "T9")
        h.pass_run(t9.run_id)
        t2 = h.active(usecase, "T2")
        assert t2.trigger_event_type == "T9.reentry.T2"
        assert t2.state == "awaiting_sign_off"
