"""T016: versions, edits, uploads and attachments (US2; FR-005 to FR-012; SC-004, SC-006)."""

import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from adlc.ledger.service import LedgerService, UnknownArtifact
from adlc.ledger.spreadsheet import InvalidUpload
from adlc.ledger.storage import AttachmentRefused
from adlc.orchestration.engine import StaleRun
from adlc.orchestration.service import NotAuthorised
from adlc.orchestration.states import InvalidTransition
from adlc.orchestration.stubs import StubAgent
from tests.support.ledger import ledger_service
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, harness, person
from tests.support.pg import PlatformDatabase

PO = person("product_owner")


def _kpis(h: Harness, run_id: str) -> list[dict]:  # type: ignore[type-arg]
    return [dict(r) for r in h.run(run_id).artifacts["kpis"]]


def _xlsx(rows: list[list[object]], sheet: str = "kpis") -> bytes:
    book = Workbook()
    ws = book.active
    assert ws is not None
    ws.title = sheet
    for row in rows:
        ws.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


@pytest.fixture
def ledger(h: Harness, tmp_path: Path) -> LedgerService:
    return ledger_service(h, tmp_path / "files")


def test_agent_versions_per_attempt(orch_template: PlatformDatabase) -> None:
    bad = {"kpis": {"baseline": "n/a"}}
    with harness(orch_template, agent=StubAgent({"T1": {1: bad}})) as h:
        usecase, t1 = walk_to(h, "T1")
        rows = h.sql(
            "SELECT version, producer_type, attempt FROM run.artifact_version WHERE run_id = :r AND artifact_id = 'kpis' ORDER BY version",
            r=t1,
        )
        assert [tuple(r) for r in rows] == [(1, "agent", 1), (2, "agent", 2)]
        unchanged = h.sql(
            "SELECT count(*) FROM run.artifact_version WHERE run_id = :r AND artifact_id = 'eval_thresholds'",
            r=t1,
        )
        assert unchanged[0][0] == 1  # same content on attempt 2: no new version


def test_person_edit_creates_a_derived_version(h: Harness, ledger: LedgerService) -> None:
    usecase, t1 = walk_to(h, "T1")
    rows = _kpis(h, t1)
    rows[0]["target"] = 7
    run = ledger.edit_artifact(PO, t1, "kpis", rows)
    history = ledger.artifact_history(t1, "kpis")
    assert [(v["version"], v["producer_type"], v["derived_from_version"]) for v in history] == [
        (1, "agent", None),
        (2, "person", 1),
    ]
    assert run.artifacts["kpis"][0]["target"] == 7
    assert ledger.edit_artifact(PO, t1, "kpis", rows).version == run.version  # unchanged: no-op
    assert len(ledger.artifact_history(t1, "kpis")) == 2
    activity = h.sql(
        "SELECT outcome FROM run.run_activity WHERE run_id = :r AND step = 'sign_off'", r=t1
    )
    assert [a[0] for a in activity] == ["edited"]
    h.pass_run(t1)
    record = h.sql("SELECT content_json FROM ledger.ledger_record WHERE run_id = :r", r=t1)[0][0]
    kpis = [a for a in record["artifacts"] if a["id"] == "kpis"][0]
    assert (kpis["version"], kpis["producer"]) == (
        2,
        {"type": "person", "id": "product_owner-person"},
    )


def test_edit_rules(h: Harness, ledger: LedgerService) -> None:
    usecase, t1 = walk_to(h, "T1")
    with pytest.raises(NotAuthorised):
        ledger.edit_artifact(person("sre"), t1, "kpis", [])
    with pytest.raises(UnknownArtifact):
        ledger.edit_artifact(PO, t1, "no_such_artifact", [])
    h.pass_run(t1)
    with pytest.raises(InvalidTransition):
        ledger.edit_artifact(PO, t1, "kpis", [])


def test_schema_validity(h: Harness, ledger: LedgerService) -> None:
    usecase, t1 = walk_to(h, "T1")
    ledger.edit_artifact(PO, t1, "kpis", [{"kpi": "x"}])
    history = ledger.artifact_history(t1, "kpis")
    assert [v["schema_valid"] for v in history] == [True, False]


def test_edit_resets_approvals_and_rechecks_controls(h: Harness, ledger: LedgerService) -> None:
    usecase, t1 = walk_to(h, "T1")  # T1 needs two approvers
    h.service.decide(person("product_owner"), t1, "pass")
    rows = _kpis(h, t1)
    rows[0]["baseline"] = "n/a"
    edited = ledger.edit_artifact(person("business_owner"), t1, "kpis", rows)
    failing = [c for c in edited.control_results if not c["passed"]]
    assert (
        failing
        and failing[0]["id"] == "CTL-T1-02"
        and "baseline is not numeric" in failing[0]["reason"]
    )
    h.service.decide(person("business_owner"), t1, "pass")
    assert h.run(t1).state == "awaiting_sign_off"  # the earlier approval no longer counts
    h.service.decide(person("product_owner"), t1, "pass")
    assert h.run(t1).final_status == "pass"


def test_edit_withdraws_a_pending_waiver(orch_template: PlatformDatabase, tmp_path: Path) -> None:
    with harness(orch_template) as h:
        ledger = ledger_service(h, tmp_path / "files")
        usecase, t5 = walk_to(h, "T5")
        so = person("security_officer")
        h.service.decide(
            so,
            t5,
            "exception",
            reason="r",
            fields={"risk_acceptance": "a", "expiry": "2099-01-01", "compensating_control": "c"},
        )
        rows = [dict(r) for r in h.run(t5).artifacts["residual_risk_register"]]
        rows[0]["rating"] = "medium"
        run = ledger.edit_artifact(so, t5, "residual_risk_register", rows)
        assert run.pending_waiver_id is None
        waiver = h.sql("SELECT status, decided_by, decision_comment FROM run.waiver")[0]
        assert tuple(waiver) == ("rejected", "system:artifact-edited", "withdrawn: artifact edited")


def test_edit_makes_an_older_decision_stale(h: Harness, ledger: LedgerService) -> None:
    usecase, t1 = walk_to(h, "T1")
    version = h.run(t1).version
    rows = _kpis(h, t1)
    rows[0]["target"] = 6
    ledger.edit_artifact(PO, t1, "kpis", rows)
    with pytest.raises(StaleRun):
        h.service.decide(PO, t1, "pass", expected_version=version)


def test_attachments_and_dedupe(h: Harness, ledger: LedgerService) -> None:
    usecase, t1 = walk_to(h, "T1")
    note = b"# KPI source\nfinance extract 2026-10"
    ledger.attach_file(PO, t1, "kpis", note, "kpi-notes.md", "text/markdown")
    ledger.attach_file(PO, t1, "eval_thresholds", note, "same-notes.md", "text/markdown")
    assert h.sql("SELECT count(*) FROM ledger.file_object")[0][0] == 1
    latest = ledger.artifact_history(t1, "kpis")[-1]
    assert [a["name"] for a in latest["attachments"]] == ["kpi-notes.md"]
    assert ledger.open_attachment(latest["attachments"][0]["content_hash"]) == note
    with pytest.raises(AttachmentRefused):
        ledger.attach_file(PO, t1, "kpis", b"MZ\x90", "tool.exe", "application/x-msdownload")


def test_spreadsheet_upload(h: Harness, ledger: LedgerService) -> None:
    usecase, t1 = walk_to(h, "T1")
    row = {**_kpis(h, t1)[0], "baseline": 12}
    data = _xlsx([list(row), list(row.values())])
    run = ledger.upload_spreadsheet(PO, t1, "kpis", data, "kpis.xlsx")
    assert run.artifacts["kpis"][0]["baseline"] == 12
    latest = ledger.artifact_history(t1, "kpis")[-1]
    assert latest["attachments"][0]["name"] == "kpis.xlsx"
    with pytest.raises(InvalidUpload):
        ledger.upload_spreadsheet(PO, t1, "kpis", b"not excel", "kpis.xlsx")


def test_identical_content_is_stored_once(h: Harness) -> None:
    a = h.submit("first")
    b = h.submit("second")
    hashes = h.sql(
        "SELECT DISTINCT content_hash FROM run.artifact_version WHERE run_id IN (:a, :b)",
        a=f"{a}/T0/run-1",
        b=f"{b}/T0/run-1",
    )
    blobs = h.sql(
        "SELECT count(*) FROM ledger.content_blob WHERE content_hash IN (SELECT content_hash FROM run.artifact_version)"
    )
    assert len(hashes) == blobs[0][0]


def test_human_edit_share(h: Harness, ledger: LedgerService) -> None:
    usecase, t1 = walk_to(h, "T1")
    rows = _kpis(h, t1)
    rows[0]["target"] = 6
    ledger.edit_artifact(PO, t1, "kpis", rows)
    share = h.sql(
        "SELECT count(DISTINCT artifact_id) FILTER (WHERE producer_type = 'person')::float / count(DISTINCT artifact_id) "
        "FROM run.artifact_version WHERE run_id = :r",
        r=t1,
    )[0][0]
    assert share == pytest.approx(1 / 9)
