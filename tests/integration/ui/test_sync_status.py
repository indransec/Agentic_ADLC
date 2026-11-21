"""019 US2: the board sync's status for its operator (FR-004 to FR-006)."""

from __future__ import annotations

from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from tests.support.api import Api
from tests.support.board import enable_board
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness
from tests.support.ui import go, open_ui, sign_in

COE = "adlc_coe"


def _status(api: Api, role: str = COE) -> AppTest:
    at = go(sign_in(open_ui(api), role), "Sync status")
    assert not at.exception, at.exception
    return at


def _metrics(at: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in at.metric}


def test_the_coe_sees_the_health_and_the_last_reconciliation(h: Harness, api: Api) -> None:
    usecase, _ = walk_to(h, "T1")
    enable_board(api)
    report = api.post(COE, "/board/reconciliations").json()
    at = _status(api)
    metrics = _metrics(at)
    for label in (
        "Last poll",
        "Inbound watermark age",
        "Reverted board changes",
        "Outbound pending",
        "Oldest pending",
        "Dead-lettered use cases",
    ):
        assert label in metrics, label
    assert metrics["Dead-lettered use cases"] == "0"
    headings = [s.value for s in at.subheader]
    assert headings == ["Refused board changes", "Board deliveries dead-lettered", "Reconciliation"]
    assert any(f"number {report['id']}" in c.value for c in at.caption)
    assert any(f"{report['created_items']} created" in t.value for t in at.text)
    assert any("Dead letters page" in c.value for c in at.caption)  # which re-queue is which


def test_reconcile_now_needs_the_confirmation(h: Harness, api: Api) -> None:
    walk_to(h, "T1")
    enable_board(api)
    at = _status(api)
    assert at.button(key="sync_reconcile").disabled
    at.checkbox(key="sync_reconcile_sure").check().run()
    at.button(key="sync_reconcile").click().run()
    assert not at.exception, at.exception
    assert any("Reconciliation finished" in s.value for s in at.success)
    assert any("items checked" in t.value for t in at.text)
    assert api.get(COE, "/board/health").json()["last_reconciliation"] is not None


def test_requeue_a_dead_lettered_use_case(h: Harness, api: Api) -> None:
    usecase, _ = walk_to(h, "T1")
    enable_board(api)
    api.post(COE, "/board/reconciliations")
    with h.owner.begin() as conn:  # the projector gave up after its retries
        conn.execute(
            text(
                "INSERT INTO board_delivery (usecase_id, dirty_since, attempts, dead_lettered_at, "
                "last_error) VALUES (:u, :n, 6, :n, 'board unreachable') "
                "ON CONFLICT (usecase_id) DO UPDATE SET dirty_since = :n, attempts = 6, "
                "dead_lettered_at = :n, last_error = 'board unreachable'"
            ),
            {"u": usecase, "n": h.clock.now()},
        )
    at = _status(api)
    assert _metrics(at)["Dead-lettered use cases"] == "1"
    assert usecase in [t.value for t in at.text]
    at.button(key=f"sync_requeue:{usecase}").click().run()
    assert not at.exception, at.exception
    assert any("Re-queued" in s.value for s in at.success)
    assert api.get(COE, "/board/health").json()["dead_lettered"] == []


def test_with_the_sync_off_the_page_says_so(api: Api) -> None:
    at = _status(api)
    assert any("board sync is off" in i.value for i in at.info)
    assert not at.metric and not [b for b in at.button if b.key == "sync_reconcile"]


def test_others_are_not_offered_the_page(h: Harness, api: Api) -> None:
    enable_board(api)
    at = _status(api, "product_owner")
    assert any("operated by the CoE role" in i.value for i in at.info)
    assert not at.metric
    assert api.get("product_owner", "/board/health").status_code == 403
