"""T016: inbox, run detail and the decision form in the web application (US2)."""

from streamlit.testing.v1 import AppTest

from adlc.orchestration.interfaces import Recommendation
from tests.support.api import Api
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness
from tests.support.ui import frame, go, open_item, open_ui, sign_in, texts

SECTIONS = [
    "Artifacts",
    "Prerequisites",
    "Control results",
    "Reviewer recommendation",
    "Prior rework comments",
    "Clarifications",
    "Approvals so far",
    "Waiver",
    "Cost",
    "Activity",
    "Evidence",
    "Decision",
]


def open_run(at: AppTest, run_id: str) -> AppTest:
    return open_item(at, run_id)


def test_inbox_detail_and_pass(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    at = open_run(sign_in(open_ui(api), "product_owner"), run)
    assert not at.exception, at.exception
    assert [s.value for s in at.subheader] == SECTIONS
    assert at.radio(key=f"decision:{run}").options == ["pass", "rework", "exception", "terminate"]
    at.button(key=f"submit:{run}").click()
    at = at.run()
    assert [s.value for s in at.success] == ["Decision recorded"], [e.value for e in at.error]
    rows = h.sql("SELECT person FROM run.sign_off WHERE run_id = :r", r=run)
    assert [r[0] for r in rows] == ["product_owner-person"]


def test_reason_field_follows_the_recommendation(h: Harness, api: Api) -> None:
    h.reviewer.script = {
        "T1": {1: Recommendation("rework", reason="no metric", root_cause="requirement")}
    }
    _, run = walk_to(h, "T1")
    at = open_run(sign_in(open_ui(api), "product_owner"), run)
    labels = [t.label for t in at.text_area]
    assert "Reason" in labels  # pass differs from rework
    at.radio(key=f"decision:{run}").set_value("rework")
    at = at.run()
    assert "Reason" not in [t.label for t in at.text_area]
    assert at.selectbox(key=f"cause:{run}").options == ["requirement", "qualification"]


def test_stale_answer_reloads_with_a_message(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    at = open_run(sign_in(open_ui(api), "product_owner"), run)
    # Someone else acts first: the business owner passes through the API.
    version = api.get("business_owner", f"/runs/{run}").json()["run"]["version"]
    answer = api.post(
        "business_owner",
        f"/runs/{run}/decisions",
        json={"decision": "pass", "expected_version": version},
    )
    assert answer.status_code == 200
    at.button(key=f"submit:{run}").click()
    at = at.run()
    shown = ([s.value for s in at.success], [e.value for e in at.error], texts(at)[-3:])
    assert at.warning and "changed since you opened it" in at.warning[0].value, shown
    assert not at.exception


def test_plain_text_for_agent_text(h: Harness, api: Api) -> None:
    payload = "<script>alert(1)</script> [click](http://evil.example)"
    h.reviewer.script = {"T1": {1: Recommendation("pass", reason=payload)}}
    _, run = walk_to(h, "T1")
    at = open_run(sign_in(open_ui(api), "product_owner"), run)
    assert payload in texts(at)
    assert all(payload not in m.value for m in at.markdown)


def test_inbox_groups_by_kind_and_marks_controls_being_rerun(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    shown = api.get("product_owner", f"/runs/{run}").json()
    rows = next(a for a in shown["artifacts"] if a["id"] == "kpis")["rows"]
    rows[0]["target"] = 42
    edited = api.put(
        "product_owner",
        f"/runs/{run}/artifacts/kpis",
        json={"rows": rows, "expected_version": shown["run"]["version"]},
    )
    assert edited.status_code == 200  # the worker has not re-run the controls yet
    at = go(sign_in(open_ui(api), "business_owner"), "Inbox")
    assert not at.exception, at.exception
    assert [s.value for s in at.subheader] == ["Sign-offs"]
    assert "controls being re-run" in list(frame(at, "note")["note"])
