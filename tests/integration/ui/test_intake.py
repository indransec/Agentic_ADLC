"""T011: sign-in, intake and journey in the web application, through the real API (US1)."""

from tests.support.api import Api
from tests.support.orchestration import Harness
from tests.support.ui import frame, go, open_ui, sign_in, texts

INTAKE = "Claims handlers spend twelve minutes triaging each claim before an assessor. " * 4


def test_sign_in_submit_and_follow(h: Harness, api: Api) -> None:
    at = open_ui(api)
    assert at.text_input(key="account") is not None and not at.exception
    at = sign_in(at, "business_owner")
    assert "business_owner" in " ".join(texts(at))
    at = go(at, "New use case")
    at.text_input(key="intake_name").input("Claims triage")
    at.text_area(key="intake_text").input(INTAKE)
    at.button[0].click()
    at = at.run()
    assert not at.exception, at.exception
    assert [s.value for s in at.success] == ["Submitted"]
    usecase = at.session_state["usecase_id"]
    h.drain()
    at = go(at, "Use cases")
    runs = frame(at, "terminal")
    assert list(runs["terminal"]) == ["T0"] and list(runs["state"]) == ["awaiting_sign_off"]
    assert at.selectbox(key="journey_usecase").value == usecase


def test_sign_out_and_expired_session(api: Api) -> None:
    at = sign_in(open_ui(api), "business_owner")
    at.button(key="sign_out").click()
    at = at.run()
    assert at.session_state["client"].token is None
    assert at.text_input(key="account") is not None
    at = sign_in(at, "business_owner")
    at.session_state["client"].token = "expired-or-forged-token"
    at = go(at, "Use cases")
    assert at.session_state["client"].token is None  # back to sign-in, nothing kept
    assert at.text_input(key="account") is not None and not at.exception


def test_refused_submission_shows_the_reason(api: Api) -> None:
    at = go(sign_in(open_ui(api), "sre"), "New use case")
    at.text_input(key="intake_name").input("x")
    at.text_area(key="intake_text").input(INTAKE)
    at.button[0].click()
    at = at.run()
    assert at.error and "not allowed" in at.error[0].value
    assert any("submitting a use case needs one of" in t for t in texts(at))
