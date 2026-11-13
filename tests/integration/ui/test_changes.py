"""T010 (012 FR-012): the ITSM owner approves a change request from the inbox."""

from tests.integration.api.test_changes_api import APPROVER, _raise
from tests.support.api import Api
from tests.support.orchestration import Harness
from tests.support.ui import go, open_ui, sign_in


def test_approver_decides_a_change_in_the_inbox(h: Harness, api: Api) -> None:
    change = _raise(h)
    at = go(sign_in(open_ui(api), APPROVER), "Inbox")
    assert not at.exception, at.exception
    assert "Change requests" in [s.value for s in at.subheader]
    at.radio(key=f"change_decision:{change}").set_value("approve")
    at.text_area(key=f"change_comment:{change}").input("window agreed with the service owner")
    at.button(key=f"change_submit:{change}").click()
    at = at.run()
    assert f"{change} approved" in [s.value for s in at.success], [e.value for e in at.error]
    assert api.get(APPROVER, "/changes").json() == []


def test_others_see_no_change_requests(h: Harness, api: Api) -> None:
    _raise(h)
    at = go(sign_in(open_ui(api), "business_owner"), "Inbox")
    assert "Change requests" not in [s.value for s in at.subheader]
