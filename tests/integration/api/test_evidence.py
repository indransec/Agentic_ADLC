"""T028: evidence in the run detail and ledger verification through the API (US5; FR-019)."""

from tests.support.api import Api
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness


def test_run_detail_carries_the_evidence(h: Harness, api: Api) -> None:
    usecase, _ = walk_to(h, "T2")
    closed = f"{usecase}/T1/run-1"
    shown = api.get("sre", f"/runs/{closed}").json()
    assert shown["timeline"] and shown["checks"] is not None
    assert all(a["version"] is not None for a in shown["artifacts"] if a["rows"] is not None)
    assert shown["ledger_record"] is not None  # a closed run has its record


def test_verify_returns_the_report_and_records_the_account(h: Harness, api: Api) -> None:
    usecase, _ = walk_to(h, "T2")
    report = api.post("sre", f"/usecases/{usecase}/verify")
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["verified"] and body["scope"] == usecase and body["records_checked"] >= 2
    rows = h.sql("SELECT actor, scope FROM ledger.verification_run")
    assert [tuple(r) for r in rows] == [("sre-person", usecase)]
    assert api.post("sre", "/usecases/UC-9999/verify").status_code == 404
