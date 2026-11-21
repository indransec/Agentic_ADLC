"""019: the web app as the operations console when the board drives decisions (US1, US3, US4)."""

from __future__ import annotations

from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from adlc.ui import mode
from adlc.ui.client import ApiClient
from tests.support.api import Api
from tests.support.board import enable_board
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness
from tests.support.ui import APP, go, open_ui, sign_in

COE = "adlc_coe"
CONSOLE_SIDEBAR = ["Use cases", "Journey", "Activity", "Portfolio", "Dead letters"]
ON_THE_BOARD = ["Inbox", "New use case", "Clarification", "Escalation", "Waiver"]
EVERY_PAGE = CONSOLE_SIDEBAR + ON_THE_BOARD + ["Run", "Sync status"]
# What offering a decision, an intake or an answer looks like on the web app (SC-002)
DECIDING = {
    "Submit decision",
    "Record decision",
    "Send answers",
    "Complete escalation",
    "Record waiver decision",
    "Submit",
}


def _projected(h: Harness, api: Api, terminal: str = "T1") -> str:
    """A run awaiting sign-off, on the (fake) board."""
    _, run_id = walk_to(h, terminal)
    enable_board(api)
    api.post(COE, "/board/reconciliations")
    return run_id


def _links(at: AppTest) -> list[dict[str, Any]]:
    """Link buttons on the page: label and address."""
    return [{"label": e.proto.label, "url": e.proto.url} for e in at.get("link_button")]


def _deciding(at: AppTest) -> list[str]:
    found = [b.label for b in at.button if b.label in DECIDING]
    found += [r.label for r in at.radio if r.label == "Outcome"]
    return found


def _sidebar(at: AppTest) -> list[str]:
    return [e.proto.label for e in at.sidebar.get("page_link")]


# ------------------------------------------------------------------------------ US1


def test_the_evidence_link_opens_the_run_after_sign_in(h: Harness, api: Api) -> None:
    """The board's link opens a new session: sign in, then the run's evidence (US1-1)."""
    run_id = _projected(h, api)
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.session_state["client"] = ApiClient(api.client)
    at.query_params["run"] = run_id
    at = sign_in(at.run(), "product_owner")
    assert not at.exception, at.exception
    assert at.session_state["page"] == "Run"
    assert at.session_state["run_id"] == run_id
    assert "Artifacts" in [s.value for s in at.subheader]
    assert "Reviewer recommendation" in [s.value for s in at.subheader]
    assert not _deciding(at)
    decide = [link for link in _links(at) if link["label"] == "Decide on the board"]
    assert len(decide) == 1 and decide[0]["url"].startswith("http://board.test/items/")
    at = go(at, "Journey")  # later navigation is not pulled back to the run
    assert at.session_state["page"] == "Journey"


def test_a_run_not_on_the_board_yet(h: Harness, api: Api) -> None:
    _, run_id = walk_to(h, "T1")
    enable_board(api)  # enabled, but nothing projected
    at = sign_in(open_ui(api), "product_owner")
    at.session_state["run_id"] = run_id
    at = go(at, "Run")
    assert not at.exception, at.exception
    assert any("not on the board yet" in c.value for c in at.caption)
    assert not _deciding(at)


# ------------------------------------------------------------------------------ US3


def test_the_console_sidebar_and_home(h: Harness, api: Api) -> None:
    enable_board(api)
    at = sign_in(open_ui(api), "product_owner")
    assert not at.exception, at.exception
    assert at.session_state["page"] == "Use cases"
    assert _sidebar(at) == CONSOLE_SIDEBAR
    coe = sign_in(open_ui(api), COE)
    assert _sidebar(coe) == CONSOLE_SIDEBAR + ["Sync status"]


@pytest.mark.parametrize("page", ON_THE_BOARD)
def test_pages_now_on_the_board_say_so(h: Harness, api: Api, page: str) -> None:
    enable_board(api)
    at = go(sign_in(open_ui(api), "product_owner"), page)
    assert not at.exception, at.exception
    assert any("made on the board now" in i.value for i in at.info)
    assert _links(at) == [{"label": "Open the board", "url": "http://board.test"}]


def test_no_page_offers_a_decision_in_console_mode(h: Harness, api: Api) -> None:
    """SC-002: every registered page, opened in console mode, as an approver and as the CoE."""
    run_id = _projected(h, api)
    for role in ("product_owner", COE):
        at = sign_in(open_ui(api), role)
        at.session_state["run_id"] = run_id
        for page in EVERY_PAGE:
            at = go(at, page)
            assert not at.exception, (role, page, at.exception)
            assert _deciding(at) == [], (role, page)


# ------------------------------------------------------------------------------ US4


def test_inbox_mode_is_unchanged_plus_sync_status_for_the_coe(api: Api) -> None:
    at = sign_in(open_ui(api), "product_owner")
    assert at.session_state["page"] == "Inbox"
    assert _sidebar(at) == ["Inbox", "New use case"] + CONSOLE_SIDEBAR
    assert _sidebar(sign_in(open_ui(api), COE))[-1] == "Sync status"


def test_the_mode_is_read_again_after_a_minute(
    h: Harness, api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = {"now": 1000.0}
    monkeypatch.setattr(mode, "now", lambda: clock["now"])
    at = sign_in(open_ui(api), "product_owner")
    assert at.session_state["page"] == "Inbox"
    enable_board(api)
    at = go(at, "Journey")
    assert "Inbox" in _sidebar(at)  # within the minute: still the inbox
    clock["now"] += mode.REREAD_SECONDS + 1
    at = go(at, "Journey")
    assert _sidebar(at) == CONSOLE_SIDEBAR


def test_an_api_error_keeps_the_last_mode(
    h: Harness, api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = {"now": 1000.0}
    monkeypatch.setattr(mode, "now", lambda: clock["now"])
    enable_board(api)
    at = sign_in(open_ui(api), "product_owner")
    assert _sidebar(at) == CONSOLE_SIDEBAR
    original = api.client.get

    def failing(path: str, *args: Any, **kwargs: Any) -> Any:
        if path.startswith("/board/mode"):
            return original("/board/no-such-route", *args, **kwargs)  # an error answer
        return original(path, *args, **kwargs)

    monkeypatch.setattr(api.client, "get", failing)
    clock["now"] += mode.REREAD_SECONDS + 1
    at = go(at, "Journey")
    assert not at.exception, at.exception
    assert _sidebar(at) == CONSOLE_SIDEBAR  # the last known mode
    assert any("could not be read" in c.value for c in at.sidebar.caption)


def test_a_decision_through_the_api_is_still_accepted(h: Harness, api: Api) -> None:
    """FR-009: the console changes the web app's offer only."""
    run_id = _projected(h, api)
    detail = api.get("product_owner", f"/runs/{run_id}").json()
    answer = api.post(
        "product_owner",
        f"/runs/{run_id}/decisions",
        json={
            "decision": "rework",
            "expected_version": detail["run"]["version"],
            "comment": "gaps",
            "root_cause": "requirement",
            "reason": "KPI missing",
            "fields": {},
        },
    )
    assert answer.status_code in (200, 201, 202), answer.text
