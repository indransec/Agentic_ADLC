"""T009 (012 FR-012, contracts/api-changes.md): change requests are decided in the inbox by the
ITSM server's owner role; a decision is a new version of the change record."""

from typing import Any

from adlc.tools.enterprise.records import EnterpriseStore
from adlc.tools.token import Claims
from tests.support.api import Api
from tests.support.orchestration import Harness

APPROVER = "release_manager"  # the registry's servicenow owner role (adlc-specs content)


def _raise(h: Harness, usecase: str = "UC-0001") -> str:
    claims = Claims(f"{usecase}/T6/run-1", usecase, "T6", 1, ())
    body = {
        "summary": "Release the triage agent",
        "window_start": "2026-11-12T10:00:00+00:00",
        "window_end": "2026-11-12T18:00:00+00:00",
        "risk": "low",
        "plan": "shadow, canary, full",
        "state": "new",
    }
    return str(EnterpriseStore(h.app).add("servicenow", "change", "CHG", claims, body)["id"])


def _listed(api: Api, role: str) -> list[dict[str, Any]]:
    answer = api.get(role, "/changes")
    assert answer.status_code == 200, answer.text
    found: list[dict[str, Any]] = answer.json()
    return found


def test_the_approver_sees_and_approves_a_change(h: Harness, api: Api) -> None:
    change = _raise(h)
    assert [c["change_id"] for c in _listed(api, APPROVER)] == [change]
    assert _listed(api, "business_owner") == []

    answer = api.post(
        APPROVER, f"/changes/{change}/decision", json={"approve": True, "comment": "ok"}
    )
    assert answer.status_code == 200, answer.text
    decided = answer.json()
    assert decided["state"] == "approved" and decided["decided_by"] == f"{APPROVER}-person"
    assert decided["record_version"] == 2 and decided["comment"] == "ok"
    assert _listed(api, APPROVER) == []  # decided: no longer waiting


def test_a_rejection_is_recorded(h: Harness, api: Api) -> None:
    change = _raise(h)
    answer = api.post(
        APPROVER, f"/changes/{change}/decision", json={"approve": False, "comment": "no"}
    )
    assert answer.status_code == 200 and answer.json()["state"] == "rejected"


def test_refusals(h: Harness, api: Api) -> None:
    change = _raise(h)
    other = api.post("business_owner", f"/changes/{change}/decision", json={"approve": True})
    assert other.status_code == 403
    assert (
        api.post(APPROVER, "/changes/CHG-999/decision", json={"approve": True}).status_code == 404
    )
    assert (
        api.post(APPROVER, f"/changes/{change}/decision", json={"approve": True}).status_code == 200
    )
    again = api.post(APPROVER, f"/changes/{change}/decision", json={"approve": False})
    assert again.status_code == 409  # already decided


def test_no_session_no_changes(api: Api) -> None:
    assert api.client.get("/changes").status_code == 401
    assert api.client.post("/changes/CHG-1/decision", json={"approve": True}).status_code == 401
