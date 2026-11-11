"""T030: text from agents and people is never rendered as Markdown or HTML (FR-013, research R-07).

Payloads go in through the intake, a rework comment, reviewer findings, a clarification answer, an
artifact cell and an attachment name. On every page that shows them, no Markdown-capable element
(markdown, captions, headings, alerts, widget labels) carries any of them.
"""

from typing import Any

from streamlit.testing.v1 import AppTest

from adlc.orchestration.interfaces import Clarification, Recommendation
from tests.support.api import Api
from tests.support.orchestration import Harness
from tests.support.ui import go, open_ui, sign_in, texts

PAYLOAD = "<script>alert(1)</script><b>bold</b>[click](http://evil.example)"
INTAKE = " ".join([PAYLOAD] * 4)  # T0 needs at least 200 characters
FILE_NAME = "<img src=x onerror=alert(1)>[c](javascript:x).md"
MARKERS = ("<script>", "<b>", "[click]", "<img", "[c]")
ARTIFACT = "kpis"  # an artifact of the terminal under test; T1 declares it in adlc-specs


def rendered(at: AppTest) -> list[str]:
    """Every value or label that Streamlit renders as Markdown or HTML."""
    found: list[str] = []
    for group in (
        at.markdown,
        at.caption,
        at.title,
        at.header,
        at.subheader,
        at.success,
        at.error,
        at.warning,
        at.info,
    ):
        found += [str(e.value) for e in group]
    found += [str(getattr(e, "body", "")) for e in at.get("html")]
    for kind in (
        "button",
        "download_button",
        "text_input",
        "text_area",
        "selectbox",
        "radio",
        "toggle",
        "file_uploader",
    ):
        found += [str(getattr(e, "label", "")) for e in at.get(kind)]
    return found


def frames(at: AppTest) -> str:
    return " ".join(e.value.to_string() for e in at.dataframe)


def assert_plain(at: AppTest) -> None:
    assert not at.exception, at.exception
    leaks = [v for v in rendered(at) if any(m in v for m in MARKERS)]
    assert leaks == []


def page(api: Api, role: str, name: str, **state: Any) -> AppTest:
    at = sign_in(open_ui(api), role)
    for key, value in state.items():
        at.session_state[key] = value
    return go(at, name)


def test_text_from_agents_and_people_is_plain(h: Harness, api: Api) -> None:
    h.reviewer.script = {"T1": {2: Recommendation("pass", findings=(PAYLOAD,), reason=PAYLOAD)}}
    h.agent.script = {"T2": {1: Clarification((PAYLOAD,))}}
    usecase = api.post(
        "business_owner", "/usecases", json={"name": "Rendering", "intake_text": INTAKE}
    ).json()["usecase_id"]
    h.drain()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
    first = h.active(usecase, "T1").run_id
    version = api.get("product_owner", f"/runs/{first}").json()["run"]["version"]
    reworked = api.post(
        "product_owner",
        f"/runs/{first}/decisions",
        json={
            "decision": "rework",
            "comment": PAYLOAD,
            "root_cause": "requirement",
            "reason": PAYLOAD,
            "fields": {"owner_comment": PAYLOAD},
            "expected_version": version,
        },
    )
    assert reworked.status_code == 200, reworked.text
    h.drain()
    run = h.active(usecase, "T1").run_id
    shown = api.get("product_owner", f"/runs/{run}").json()
    rows = next(a for a in shown["artifacts"] if a["id"] == ARTIFACT)["rows"]
    rows[0]["kpi"] = PAYLOAD
    edited = api.put(
        "product_owner",
        f"/runs/{run}/artifacts/{ARTIFACT}",
        json={"rows": rows, "expected_version": shown["run"]["version"]},
    )
    assert edited.status_code == 200
    attached = api.post(
        "product_owner",
        f"/runs/{run}/artifacts/{ARTIFACT}/attachments",
        files={"file": (FILE_NAME, b"notes", "text/markdown")},
        data={"expected_version": str(edited.json()["run"]["version"])},
    )
    assert attached.status_code == 200, attached.text
    h.drain()

    journey = page(api, "business_owner", "Use cases")
    assert_plain(journey)
    assert INTAKE in texts(journey)  # the intake, as plain text

    detail = page(api, "product_owner", "Run", run_id=run)
    assert_plain(detail)
    assert PAYLOAD in texts(detail)  # the reviewer's reason and findings
    assert FILE_NAME in texts(detail)
    assert PAYLOAD in frames(detail)  # the rework comment and the artifact cell, as table text

    h.pass_run(run)
    t2 = h.active(usecase, "T2").run_id
    clarification = f"{t2}/clar-1"
    answered = api.post(
        "engineering_lead", f"/clarifications/{clarification}/answers", json={"answers": [PAYLOAD]}
    )
    assert answered.status_code == 200
    asked = page(
        api, "engineering_lead", "Clarification", run_id=t2, clarification_id=clarification
    )
    assert_plain(asked)
    assert texts(asked).count(PAYLOAD) >= 2  # the question and the answer
