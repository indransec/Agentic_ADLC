"""T015: the inbox and sign-off decisions through the API (US2; FR-002, FR-006 to FR-011; SC-002,
SC-004)."""

from datetime import timedelta
from typing import Any

from adlc.orchestration.interfaces import Recommendation
from tests.support.api import Api
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness

SA_8_2 = {
    "artifacts",
    "control_results",
    "recommendation",
    "prior_rework",
    "clarifications",
    "approvals",
    "timer",
    "cost",
    "timeline",
    "form",
    "run",
}
REWORK = {
    "decision": "rework",
    "comment": "the success metric is missing",
    "root_cause": "requirement",
    "fields": {"owner_comment": "add the metric"},
    "reason": "the reviewer missed the metric",  # the stub reviewer recommends pass
}


def detail(api: Api, role: str, run_id: str) -> dict[str, Any]:
    answer = api.get(role, f"/runs/{run_id}")
    assert answer.status_code == 200, answer.text
    return dict(answer.json())


def decide(api: Api, role: str, run_id: str, body: dict[str, Any]) -> Any:
    version = detail(api, role, run_id)["run"]["version"]
    return api.post(role, f"/runs/{run_id}/decisions", json={"expected_version": version, **body})


def inbox_runs(api: Api, role: str) -> list[str]:
    return [i["run_id"] for i in api.get(role, "/inbox").json() if i["kind"] == "sign_off"]


def test_inbox_shows_t1_to_its_sign_off_roles_only(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    assert run in inbox_runs(api, "product_owner") and run in inbox_runs(api, "business_owner")
    assert run not in inbox_runs(api, "sre") and run not in inbox_runs(api, "engineering_lead")
    # Two approvers: after the product owner passes, it stays with the business owner only.
    assert decide(api, "product_owner", run, {"decision": "pass"}).status_code == 200
    assert run not in inbox_runs(api, "product_owner") and run in inbox_runs(api, "business_owner")
    item = next(i for i in api.get("business_owner", "/inbox").json() if i["run_id"] == run)
    assert item["role"] == "business_owner" and item["terminal_id"] == "T1"


def test_inbox_order_soonest_due_first(h: Harness, api: Api) -> None:
    first, _ = walk_to(h, "T1")
    h.clock.advance(timedelta(minutes=5))
    second, _ = walk_to(h, "T1")
    items = [i for i in api.get("product_owner", "/inbox").json() if i["kind"] == "sign_off"]
    dues = [i["due_at"] for i in items]
    assert dues == sorted(dues) and [i["usecase_id"] for i in items][:2] == [first, second]


def test_detail_has_every_sa_8_2_section_and_prior_rework(h: Harness, api: Api) -> None:
    usecase, run = walk_to(h, "T1")
    assert decide(api, "product_owner", run, REWORK).status_code == 200
    h.drain()
    again = h.active(usecase, "T1").run_id
    assert again != run
    shown = detail(api, "product_owner", again)
    assert set(shown) >= SA_8_2
    assert [p["run_id"] for p in shown["prior_rework"]] == [run]
    prior = shown["prior_rework"][0]
    assert prior["person"] == "product_owner-person" and prior["root_cause"] == "requirement"
    assert prior["comment"] == REWORK["comment"]
    assert shown["recommendation"]["items"] and shown["timer"]["due_at"] is not None


def test_differing_from_the_reviewer_needs_a_reason(h: Harness, api: Api) -> None:
    h.reviewer.script = {
        "T1": {1: Recommendation("rework", reason="no metric", root_cause="requirement")}
    }
    _, run = walk_to(h, "T1")
    assert detail(api, "product_owner", run)["form"]["reason_required_unless"] == "rework"
    refused = decide(api, "product_owner", run, {"decision": "pass"})
    assert refused.status_code == 422 and refused.json()["kind"] == "invalid"
    assert "reason" in refused.json()["detail"]
    accepted = decide(api, "product_owner", run, {"decision": "pass", "reason": "metric agreed"})
    assert accepted.status_code == 200


def test_rework_needs_comment_and_root_cause(h: Harness, api: Api) -> None:
    usecase, run = walk_to(h, "T1")
    bare = decide(api, "product_owner", run, {"decision": "rework", "reason": "r"})
    assert bare.status_code == 422
    routed = decide(api, "product_owner", run, REWORK)
    assert routed.status_code == 200 and routed.json()["final_status"] == "rework"
    h.drain()
    assert h.active(usecase, "T1").run_number == 2  # routed back to T1 (requirement)


def test_exception_creates_a_pending_waiver(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    answer = decide(
        api,
        "product_owner",
        run,
        {
            "decision": "exception",
            "reason": "accepted with a compensating control",
            "fields": {
                "waiver_owner": "product_owner-person",
                "expiry": "2099-01-01",
                "compensating_control": "weekly manual review",
            },
        },
    )
    assert answer.status_code == 200, answer.text
    assert h.run(run).pending_waiver_id is not None
    assert detail(api, "product_owner", run)["waiver"] is not None


def test_stale_decision_changes_nothing(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    version = detail(api, "product_owner", run)["run"]["version"]
    before = h.sql("SELECT count(*) FROM run.sign_off WHERE run_id = :r", r=run)[0][0]
    stale = api.post(
        "product_owner",
        f"/runs/{run}/decisions",
        json={"decision": "pass", "expected_version": version - 1},
    )
    assert stale.status_code == 409 and stale.json()["kind"] == "stale"
    after = h.sql("SELECT count(*) FROM run.sign_off WHERE run_id = :r", r=run)[0][0]
    assert before == after and h.run(run).version == version


def test_a_body_cannot_name_another_actor(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    for extra in ({"actor": "business_owner-person"}, {"account_name": "x"}, {"roles": ["x"]}):
        refused = decide(api, "product_owner", run, {"decision": "pass", **extra})
        assert refused.status_code == 422 and refused.json()["kind"] == "invalid"
    assert decide(api, "product_owner", run, {"decision": "pass"}).status_code == 200
    rows = h.sql("SELECT person, role FROM run.sign_off WHERE run_id = :r", r=run)
    assert [tuple(r) for r in rows] == [("product_owner-person", "product_owner")]


def test_strangers_cannot_decide_and_unknown_runs_are_not_found(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    refused = decide(api, "sre", run, {"decision": "pass"})
    assert refused.status_code == 403 and refused.json()["kind"] == "not_allowed"
    assert api.get("sre", "/runs/UC-9999/T1/run-1").status_code == 404
