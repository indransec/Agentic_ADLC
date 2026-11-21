"""016 T045, T049: board sync health, reconciliation and requeue over the API (CoE only)."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr

from adlc.config.settings import BoardSettings
from adlc.engagement.wiring import build
from tests.support.api import Api
from tests.support.board import EVIDENCE, MAPPING_FILE, SERVICE, fake_board, mapping
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness

COE = "adlc_coe"


def _enable(api: Api, tmp_path: Path) -> None:
    """Give the API an engagement layer over a FakeBoard (as the board process builds it)."""
    services = api.app.state.services
    accounts = services.settings.accounts_file
    settings = BoardSettings(
        env="dev",
        db_path=services.settings.db_path,
        accounts_file=accounts,
        deadletter_role=COE,
        board_enabled=True,
        board_url="http://board.test",
        board_organization="org",
        board_project="project",
        board_token=SecretStr("t" * 32),
        board_service_identity=SERVICE,
        board_evidence_url=EVIDENCE,
        board_mapping_file=MAPPING_FILE,
    )
    api.app.state.engagement = build(settings, services=services, board=fake_board(mapping()))


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
