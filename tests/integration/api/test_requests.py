"""T024: clarifications, escalations, waivers and dead letters through the API (US4; FR-015 to
FR-018)."""

from datetime import timedelta
from typing import Any

from sqlalchemy import text

from adlc.orchestration.interfaces import Clarification
from tests.support.api import Api
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness

EXCEPTION = {
    "decision": "exception",
    "reason": "accepted with a compensating control",
    "fields": {
        "waiver_owner": "product_owner-person",
        "expiry": "2099-01-01",
        "compensating_control": "weekly manual review",
    },
}


def items(api: Api, role: str, kind: str) -> list[dict[str, Any]]:
    return [i for i in api.get(role, "/inbox").json() if i["kind"] == kind]


def version(api: Api, run: str) -> int:
    return int(api.get("sre", f"/runs/{run}").json()["run"]["version"])


def test_clarification_for_the_addressed_role_resumes_the_run(h: Harness, api: Api) -> None:
    h.agent.script = {"T2": {1: Clarification(("Which channels are in scope?",))}}
    _, run = walk_to(h, "T2")
    asked = items(api, "engineering_lead", "clarification")  # T2's first R role
    assert [i["run_id"] for i in asked] == [run]
    assert items(api, "product_owner", "clarification") == []
    path = f"/clarifications/{asked[0]['id']}/answers"
    refused = api.post("product_owner", path, json={"answers": ["web"]})
    assert refused.status_code == 403
    answered = api.post("engineering_lead", path, json={"answers": ["web", "email"]})
    assert answered.status_code == 200, answered.text
    again = api.post("engineering_lead", path, json={"answers": ["phone"]})
    assert again.status_code == 409 and again.json()["kind"] == "wrong_state"
    h.drain()
    assert h.run(run).state == "awaiting_sign_off"  # the same run resumed
    assert items(api, "engineering_lead", "clarification") == []
    missing = api.post(
        "engineering_lead",
        "/clarifications/UC-9999/T2/run-1/clar-1/answers",
        json={"answers": ["x"]},
    )
    assert missing.status_code == 404


def test_escalation_completion_leads_to_sign_off(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    h.clock.advance(timedelta(days=10, seconds=1))  # T1's escalate_after
    h.drain()
    assert h.run(run).state == "escalated"
    assert [i["run_id"] for i in items(api, "product_owner", "escalation")] == [run]
    assert items(api, "business_owner", "escalation") == []  # not accountable
    assert api.get("product_owner", f"/runs/{run}").json()["form"]["can_complete_escalation"]
    path = f"/runs/{run}/escalation"
    current = version(api, run)
    body: dict[str, Any] = {"artifacts": {}, "expected_version": current}
    assert api.post("business_owner", path, json=body).status_code == 403
    stale = api.post("product_owner", path, json={**body, "expected_version": current - 1})
    assert stale.status_code == 409 and stale.json()["kind"] == "stale"
    done = api.post("product_owner", path, json=body)
    assert done.status_code == 200, done.text
    h.drain()
    assert h.run(run).state == "awaiting_sign_off"


def test_waiver_for_approvers_other_than_the_proposer(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    proposed = api.post(
        "business_owner",
        f"/runs/{run}/decisions",
        json={**EXCEPTION, "expected_version": version(api, run)},
    )
    assert proposed.status_code == 200, proposed.text
    waiver = h.run(run).pending_waiver_id
    listed = items(api, "product_owner", "waiver")
    assert [(i["id"], i["run_id"]) for i in listed] == [(waiver, run)]
    assert items(api, "business_owner", "waiver") == []
    decided = api.post(
        "product_owner",
        f"/waivers/{waiver}/decision",
        json={"approve": False, "comment": "no control owner yet"},
    )
    assert decided.status_code == 200, decided.text
    row = h.sql(
        "SELECT status, decided_by, decision_comment FROM run.waiver WHERE waiver_id = :w", w=waiver
    )[0]
    assert tuple(row) == ("rejected", "product_owner-person", "no control owner yet")
    assert (
        api.post("product_owner", "/waivers/WVR-9999/decision", json={"approve": True}).status_code
        == 404
    )


def test_the_proposer_cannot_decide_their_waiver(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    api.post(
        "product_owner",
        f"/runs/{run}/decisions",
        json={**EXCEPTION, "expected_version": version(api, run)},
    )
    waiver = h.run(run).pending_waiver_id
    assert items(api, "product_owner", "waiver") == []
    refused = api.post("product_owner", f"/waivers/{waiver}/decision", json={"approve": True})
    assert refused.status_code == 403


def test_dead_letters_for_the_coe_only(h: Harness, api: Api) -> None:
    h.submit()
    with h.owner.begin() as conn:
        conn.execute(
            text(
                "UPDATE events.outbox_event SET dead_lettered_at = now(), "
                "last_error = 'test' WHERE event_type = 'usecase.submitted'"
            )
        )
    assert api.get("sre", "/dead-letters").status_code == 403
    assert items(api, "sre", "dead_letter") == []
    (dead,) = api.get("adlc_coe", "/dead-letters").json()
    assert [i["id"] for i in items(api, "adlc_coe", "dead_letter")] == [dead["event_id"]]
    assert api.post("sre", f"/dead-letters/{dead['event_id']}/requeue").status_code == 403
    assert api.post("adlc_coe", f"/dead-letters/{dead['event_id']}/requeue").status_code == 204
    again = api.post("adlc_coe", f"/dead-letters/{dead['event_id']}/requeue")
    assert again.status_code == 404
    assert api.get("adlc_coe", "/dead-letters").json() == []
