"""T045: a blocked run in the web application (change request 2026-11-11)."""

from tests.support.api import Api
from tests.support.orchestration import Harness
from tests.support.ui import frame, go, open_item, open_ui, sign_in

SHORT = "Too short to describe the problem."


def test_blocked_run_shows_why_and_can_be_terminated(h: Harness, api: Api) -> None:
    usecase = api.post(
        "business_owner", "/usecases", json={"name": "Short", "intake_text": SHORT}
    ).json()["usecase_id"]
    h.drain()
    run = f"{usecase}/T0/run-1"
    at = go(sign_in(open_ui(api), "business_owner"), "Inbox")
    assert "Blocked runs" in [s.value for s in at.subheader]
    at = open_item(at, run)
    assert not at.exception, at.exception
    assert at.warning and "unmet prerequisite" in at.warning[0].value
    prerequisites = frame(at, "on_missing")
    unmet = prerequisites[prerequisites["passed"] == False]  # noqa: E712 - a pandas mask
    assert len(unmet) >= 1 and all(unmet["description"])
    assert at.radio(key=f"decision:{run}").options == ["terminate"]
    at.text_area(key=f"comment:{run}").input("resubmitting with a full description")
    at.button(key=f"submit:{run}").click()
    at = at.run()
    assert "Decision recorded" in [s.value for s in at.success], [e.value for e in at.error]
