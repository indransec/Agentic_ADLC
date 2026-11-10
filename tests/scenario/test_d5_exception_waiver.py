"""D-5: a T5 exception proposed by the owner, approved by the risk owner, routes to T6."""

from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person


def test_d5(h: Harness) -> None:
    usecase, t5 = walk_to(h, "T5")
    h.service.decide(
        person("security_officer"),
        t5,
        "exception",
        reason="residual risk accepted",
        fields={
            "risk_acceptance": "accepted",
            "expiry": "2099-06-30",
            "compensating_control": "HITL review",
        },
    )
    waiver = h.run(t5).pending_waiver_id
    assert waiver is not None
    h.service.decide_waiver(person("risk_owner"), waiver, True, "accepted until mid-2099")
    h.drain()
    assert h.run(t5).final_status == "exception"
    t6 = h.active(usecase, "T6")
    assert t6.trigger_event_type == "T5.exception"
    assert t6.trigger_context["status"] == "exception"
