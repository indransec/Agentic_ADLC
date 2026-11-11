"""T025: clarification, escalation, waiver and dead-letter pages (US4)."""

from datetime import timedelta
from typing import Any

import pytest
import streamlit
from sqlalchemy import text

from adlc.orchestration.interfaces import Clarification
from tests.support.api import Api
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness
from tests.support.ui import go, open_item, open_ui, sign_in, texts

QUESTION = "Which channels are in scope?"


def success(at: Any) -> list[str]:
    return [s.value for s in at.success]


def test_answer_a_clarification(h: Harness, api: Api) -> None:
    h.agent.script = {"T2": {1: Clarification((QUESTION,))}}
    _, run = walk_to(h, "T2")
    clarification = f"{run}/clar-1"
    at = open_item(sign_in(open_ui(api), "engineering_lead"), clarification)
    assert not at.exception, at.exception
    assert QUESTION in texts(at)
    at.text_area(key=f"answer:{clarification}:0").input("web and email")
    at.button(key=f"send:{clarification}").click()
    at = at.run()
    assert "Answers sent" in success(at), [e.value for e in at.error]
    h.drain()
    assert h.run(run).state == "awaiting_sign_off"


def test_complete_an_escalation(h: Harness, api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        streamlit, "data_editor", lambda data, **kw: data
    )  # AppTest cannot drive it
    _, run = walk_to(h, "T1")
    h.clock.advance(timedelta(days=10, seconds=1))
    h.drain()
    at = open_item(sign_in(open_ui(api), "product_owner"), run)
    assert not at.exception, at.exception
    assert at.session_state["page"] == "Escalation"
    at.button(key=f"complete:{run}").click()
    at = at.run()
    assert "Escalation completed" in success(at), [e.value for e in at.error]
    h.drain()
    assert h.run(run).state == "awaiting_sign_off"


def test_decide_a_waiver(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    version = api.get("business_owner", f"/runs/{run}").json()["run"]["version"]
    proposed = api.post(
        "business_owner",
        f"/runs/{run}/decisions",
        json={
            "decision": "exception",
            "reason": "accepted with a control",
            "expected_version": version,
            "fields": {
                "waiver_owner": "product_owner-person",
                "expiry": "2099-01-01",
                "compensating_control": "weekly manual review",
                "risk_acceptance": "accepted for the pilot only",
            },
        },
    )
    assert proposed.status_code == 200
    waiver = h.run(run).pending_waiver_id
    assert waiver is not None
    at = open_item(sign_in(open_ui(api), "product_owner"), waiver)
    assert not at.exception, at.exception
    assert "weekly manual review" in texts(at)
    assert "accepted for the pilot only" in texts(at)  # every proposal field (FR-017)
    at.text_area(key=f"waiver_comment:{waiver}").input("control is credible")
    at.button(key=f"waiver_send:{waiver}").click()
    at = at.run()
    assert "Waiver decision recorded" in success(at), [e.value for e in at.error]
    status = h.sql("SELECT status FROM run.waiver WHERE waiver_id = :w", w=waiver)[0][0]
    assert status == "approved"


def test_dead_letters_for_the_coe(h: Harness, api: Api) -> None:
    h.submit()
    with h.owner.begin() as conn:
        conn.execute(
            text(
                "UPDATE events.outbox_event SET dead_lettered_at = now() "
                "WHERE event_type = 'usecase.submitted'"
            )
        )
    other = go(sign_in(open_ui(api), "sre"), "Dead letters")
    assert any("CoE" in c.value for c in other.caption) and not other.exception
    at = go(sign_in(open_ui(api), "adlc_coe"), "Dead letters")
    assert not at.exception, at.exception
    at.button(key="dead_requeue").click()
    at = at.run()
    assert "Re-queued" in success(at), [e.value for e in at.error]
    assert api.get("adlc_coe", "/dead-letters").json() == []
