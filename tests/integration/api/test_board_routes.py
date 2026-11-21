"""016 T045, T049: board sync health, reconciliation and requeue over the API (CoE only)."""

from __future__ import annotations

from pathlib import Path

from tests.support.api import Api
from tests.support.board import enable_board
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness

COE = "adlc_coe"


def _enable(api: Api, tmp_path: Path) -> None:
    enable_board(api, COE)


def test_health_is_for_the_coe_only(api: Api) -> None:
    assert api.get("product_owner", "/board/health").status_code == 403
    answer = api.get(COE, "/board/health")
    assert answer.status_code == 200
    body = answer.json()
    assert (
        body["enabled"] is False and body["outbound_pending"] == 0 and body["dead_lettered"] == []
    )


def test_reconcile_when_disabled_is_refused(api: Api) -> None:
    assert api.post(COE, "/board/reconciliations").status_code == 422


def test_reconcile_requeue_and_reports(h: Harness, api: Api, tmp_path: Path) -> None:
    usecase, _ = walk_to(h, "T1")
    _enable(api, tmp_path)
    assert api.post("product_owner", "/board/reconciliations").status_code == 403
    report = api.post(COE, "/board/reconciliations").json()
    assert report["created_items"] >= 3 and report["outcome"] == "ok"
    again = api.get(COE, f"/board/reconciliations/{report['id']}").json()
    assert again["id"] == report["id"]
    assert api.get(COE, "/board/reconciliations/999").status_code == 404
    assert api.post(COE, f"/board/requeue/{usecase}").status_code == 404  # not dead-lettered
    health = api.get(COE, "/board/health").json()
    assert health["last_reconciliation"]["id"] == report["id"]


# ------------------------------------------------------------------ 019 the console's mode and links


def test_mode_is_inbox_when_the_sync_is_disabled(api: Api) -> None:
    body = api.get("product_owner", "/board/mode").json()
    assert body == {"mode": "inbox", "board_url": None, "can_operate": False}
    assert api.get(COE, "/board/mode").json()["can_operate"] is True
    assert api.client.get("/board/mode").status_code == 401  # signed out


def test_mode_is_console_when_the_sync_is_enabled(api: Api, tmp_path: Path) -> None:
    _enable(api, tmp_path)
    body = api.get("sre", "/board/mode").json()
    assert body == {"mode": "console", "board_url": "http://board.test", "can_operate": False}


def test_board_items_of_use_cases_and_runs(h: Harness, api: Api, tmp_path: Path) -> None:
    usecase, run_id = walk_to(h, "T1")
    assert "/" in run_id
    assert api.get("sre", f"/board/items/run/{run_id}").status_code == 404  # disabled
    _enable(api, tmp_path)
    assert api.get("sre", f"/board/items/run/{run_id}").status_code == 404  # not projected yet
    api.post(COE, "/board/reconciliations")
    for kind, object_id in (("usecase", usecase), ("run", run_id)):
        answer = api.get("sre", f"/board/items/{kind}/{object_id}")
        assert answer.status_code == 200, answer.text
        body = answer.json()
        assert body["url"] == f"http://board.test/items/{body['work_item_id']}"
    assert api.get("sre", "/board/items/sprint/1").status_code == 422
    assert (
        api.get("sre", "/board/items/change/CHG-0001").status_code == 404
    )  # 020: a kind, not yet there
    assert api.client.get(f"/board/items/run/{run_id}").status_code == 401
