"""T038: two-step exception with a waiver (FR-012a; US2/AC7)."""

import pytest

from adlc.orchestration.service import InvalidDecision, NotAuthorised
from adlc.orchestration.states import InvalidTransition
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person

T5_FIELDS = {
    "risk_acceptance": "accepted",
    "expiry": "2099-12-31",
    "compensating_control": "manual review",
}


def test_required_fields(h: Harness) -> None:
    _, run_id = walk_to(h, "T5")
    so = person("security_officer")
    with pytest.raises(InvalidDecision, match="risk_acceptance"):
        h.service.decide(
            so,
            run_id,
            "exception",
            reason="r",
            fields={"expiry": "2099-01-01", "compensating_control": "x"},
        )
    with pytest.raises(InvalidDecision, match="future"):
        h.service.decide(
            so, run_id, "exception", reason="r", fields={**T5_FIELDS, "expiry": "2001-01-01"}
        )
    assert h.sql("SELECT count(*) FROM run.waiver")[0][0] == 0


def test_propose_then_approve(h: Harness) -> None:
    usecase, run_id = walk_to(h, "T5")
    so = person("security_officer")
    h.service.decide(so, run_id, "exception", reason="known gap", fields=T5_FIELDS)
    run = h.run(run_id)
    assert run.state == "awaiting_sign_off" and run.pending_waiver_id == "WVR-0001"
    with pytest.raises(NotAuthorised):  # approver must hold set_by (risk_owner)
        h.service.decide_waiver(person("privacy_officer"), "WVR-0001", True)
    with pytest.raises(NotAuthorised):  # and differ from the proposer
        h.service.decide_waiver(person("security_officer", "risk_owner"), "WVR-0001", True)
    h.service.decide_waiver(person("risk_owner"), "WVR-0001", True, "accepted for one quarter")
    h.drain()
    assert h.run(run_id).final_status == "exception"
    waiver = h.sql("SELECT status, decided_by, recheck_at FROM run.waiver")[0]
    assert tuple(waiver) == ("approved", "risk_owner-person", ["T6", "T8"])
    assert h.active(usecase, "T6").trigger_event_type == "T5.exception"
    record = h.sql("SELECT content_json FROM ledger.ledger_record WHERE run_id = :r", r=run_id)[0][
        0
    ]
    assert record["waiver"]["waiver_id"] == "WVR-0001"


def test_reject_lets_a_new_decision_be_made(h: Harness) -> None:
    _, run_id = walk_to(h, "T5")
    so = person("security_officer")
    h.service.decide(so, run_id, "exception", reason="r", fields=T5_FIELDS)
    with pytest.raises(InvalidTransition):  # nothing else while the waiver is pending
        h.service.decide(so, run_id, "pass")
    h.service.decide_waiver(person("risk_owner"), "WVR-0001", False, "not acceptable")
    assert h.run(run_id).pending_waiver_id is None
    assert h.sql("SELECT status FROM run.waiver")[0][0] == "rejected"
    h.pass_run(run_id)
    assert h.run(run_id).final_status == "pass"
