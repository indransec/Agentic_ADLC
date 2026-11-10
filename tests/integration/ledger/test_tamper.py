"""T026: verification finds every kind of tampering (US4; FR-016 to FR-019; SC-002, SC-003, SC-007)."""

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, create_engine, text

from adlc.identity.catalogue import load_role_ids
from adlc.ledger.content import record_hash
from adlc.ledger.service import LedgerService
from adlc.orchestration import store as run_store
from adlc.orchestration.ledger import make_record
from adlc.orchestration.service import Actor
from tests.support.ledger import ledger_service
from tests.support.lifecycle import ORDER, walk_to
from tests.support.orchestration import Harness, person

ROLES = Path(__file__).resolve().parents[3] / "adlc-specs" / "shared" / "roles.yaml"
AUDITOR = person("auditor")
NOTE = b"# evidence note\nsource: finance extract"


@pytest.fixture
def ledger(h: Harness, tmp_path: Path) -> LedgerService:
    return ledger_service(h, tmp_path / "files")


@pytest.fixture
def superuser(h: Harness) -> Iterator[Engine]:
    engine = create_engine(h.db.url("postgres", h.db.superuser_password))
    yield engine
    engine.dispose()


def _tamper(engine: Engine, sql: str, **params: Any) -> None:
    """Bypass the append-only triggers, as an attacker with database superuser rights could."""
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text(sql), params)


def _key(h: Harness, usecase: str, terminal: str) -> str:
    rows = h.sql(
        "SELECT ledger_key FROM ledger.ledger_record WHERE usecase_id = :u AND ledger_key LIKE :k",
        u=usecase,
        k=f"%/{terminal}/run-1",
    )
    return str(rows[0][0])


def _lifecycle(h: Harness, ledger: LedgerService | None = None) -> str:
    """T0 to T8 all passed; with ``ledger``, T1 carries an attachment."""
    usecase, t1 = walk_to(h, "T1")
    if ledger is not None:
        ledger.attach_file(person("product_owner"), t1, "kpis", NOTE, "notes.md", "text/markdown")
    h.pass_run(t1)
    for terminal in ORDER[2:]:
        h.pass_run(h.active(usecase, terminal).run_id, {"risk_tier": "medium"})
    return usecase


def _legacy_record(conn: Connection, usecase: str, run_id: str) -> None:
    """A version-1 record as feature 003 wrote it (no content version, inline artifacts)."""
    content = {"run_id": run_id, "usecase_id": usecase, "artifacts": {"note": [{"a": 1}]}}
    record = make_record(
        ledger_key=f"{usecase}/legacy/run-1", content=content, previous_record_hash=None
    )
    run_store.insert_ledger_record(conn, record, time_now(conn))


def time_now(conn: Connection) -> Any:
    return conn.execute(text("SELECT now()")).scalar()


def test_clean_lifecycle_verifies_with_a_version_one_record(
    h: Harness, ledger: LedgerService
) -> None:
    """SC-002: a T0 to T8 lifecycle verifies, and so does a record written before feature 005."""
    legacy = h.submit("written before 005")
    with h.app.begin() as conn:
        _legacy_record(conn, legacy, h.active(legacy, "T0").run_id)
    usecase = _lifecycle(h)
    assert ledger.verify(AUDITOR, usecase).records_checked == 9
    report = ledger.verify(AUDITOR, "all")
    assert report.verified, report.breaks
    assert report.records_checked == 10


def test_altered_record_content(h: Harness, ledger: LedgerService, superuser: Engine) -> None:
    usecase = _lifecycle(h)
    key = _key(h, usecase, "T2")
    _tamper(
        superuser,
        "UPDATE ledger.ledger_record SET content_json = jsonb_set(content_json, "
        "'{final_status}', '\"rework\"') WHERE ledger_key = :k",
        k=key,
    )
    breaks = ledger.verify(AUDITOR, usecase).breaks
    assert [(b.ledger_key, b.check, b.element) for b in breaks] == [(key, "content", "record")]


def test_altered_artifact_body(h: Harness, ledger: LedgerService, superuser: Engine) -> None:
    usecase = _lifecycle(h)
    key = _key(h, usecase, "T1")
    record = h.sql("SELECT content_json FROM ledger.ledger_record WHERE ledger_key = :k", k=key)
    kpis = [a for a in record[0][0]["artifacts"] if a["id"] == "kpis"][0]
    _tamper(
        superuser,
        "UPDATE ledger.content_blob SET body = '[]'::jsonb WHERE content_hash = :h",
        h=kpis["content_hash"],
    )
    breaks = ledger.verify(AUDITOR, usecase).breaks
    assert (key, "artifact", "kpis") in [(b.ledger_key, b.check, b.element) for b in breaks]
    assert all(b.actual != [] for b in breaks)  # hashes only, never the content


def test_deleted_attachment_file(h: Harness, ledger: LedgerService) -> None:
    usecase = _lifecycle(h, ledger)
    key = _key(h, usecase, "T1")
    digest = h.sql("SELECT content_hash FROM ledger.file_object")[0][0]
    ledger.content.files.path(digest).unlink()
    breaks = ledger.verify(AUDITOR, usecase).breaks
    assert [(b.ledger_key, b.check, b.element, b.actual) for b in breaks] == [
        (key, "attachment", "kpis/notes.md", None)
    ]


def test_broken_chain(h: Harness, ledger: LedgerService, superuser: Engine) -> None:
    usecase = _lifecycle(h)
    key = _key(h, usecase, "T5")
    _tamper(
        superuser,
        "UPDATE ledger.ledger_record SET previous_record_hash = :p WHERE ledger_key = :k",
        p="sha256:" + "0" * 64,
        k=key,
    )
    breaks = ledger.verify(AUDITOR, usecase).breaks
    assert [(b.ledger_key, b.check) for b in breaks] == [(key, "chain")]


def test_package_binding(h: Harness, ledger: LedgerService, superuser: Engine) -> None:
    """A rewritten T4 record with a valid hash but a different package is still caught."""
    usecase = _lifecycle(h)
    key = _key(h, usecase, "T4")
    content = h.sql("SELECT content_json FROM ledger.ledger_record WHERE ledger_key = :k", k=key)
    forged = {**content[0][0], "bound_to": "sha256:" + "f" * 64}
    _tamper(
        superuser,
        "UPDATE ledger.ledger_record SET content_json = CAST(:c AS jsonb), content_hash = :h "
        "WHERE ledger_key = :k",
        c=json.dumps(forged),
        h=record_hash(forged),
        k=key,
    )
    breaks = ledger.verify(AUDITOR, usecase).breaks
    binding = [b for b in breaks if b.check == "binding"]
    assert [(b.ledger_key, b.element, b.actual) for b in binding] == [
        (key, "T3.candidate_package.sha256", "sha256:" + "f" * 64)
    ]
    assert {b.check for b in breaks} == {"binding", "chain"}  # T5 no longer chains to T4


def test_verification_runs_are_recorded(
    h: Harness, ledger: LedgerService, superuser: Engine
) -> None:
    first = _lifecycle(h)
    h.submit("second")
    ledger.verify(AUDITOR, first)
    ledger.verify(AUDITOR, "all")
    rows = h.sql(
        "SELECT actor, scope, records_checked, verified, breaks FROM ledger.verification_run "
        "ORDER BY verification_run_id"
    )
    assert [tuple(r)[:4] for r in rows] == [
        ("auditor-person", first, 9, True),
        ("auditor-person", "all", 9, True),
    ]
    assert rows[0][4] == []


def test_verification_is_fast(h: Harness, ledger: LedgerService) -> None:
    """SC-007: 10 closed runs with 3 attachments of 1 MB each verify in under 2 seconds."""
    everyone = Actor("all-roles", _catalogue_roles())

    def attach(run_id: str) -> None:
        run = h.run(run_id)
        artifact = next(iter(run.artifacts))
        for n in range(3):
            data = (f"{run_id}-{n}\n".encode() + b"x" * 1_000_000)[:1_000_000]
            ledger.attach_file(everyone, run_id, artifact, data, f"{n}.txt", "text/plain")

    usecase = h.submit()
    for terminal in ORDER:
        run_id = h.active(usecase, terminal).run_id
        attach(run_id)
        if terminal == "T1":  # one rework, so the use case has 10 closed runs
            h.service.decide(
                person("product_owner"),
                run_id,
                "rework",
                comment="c",
                root_cause="requirement",
                reason="r",
            )
            h.drain()
            run_id = h.active(usecase, terminal).run_id
            attach(run_id)
        h.pass_run(run_id, {"risk_tier": "medium"})
    started = time.perf_counter()
    report = ledger.verify(AUDITOR, usecase)
    elapsed = time.perf_counter() - started
    assert report.verified, report.breaks
    assert report.records_checked == 10
    assert h.sql("SELECT count(*) FROM ledger.file_object")[0][0] == 30
    assert elapsed < 2.0, f"verification took {elapsed:.2f} s"


def _catalogue_roles() -> frozenset[str]:
    return load_role_ids(ROLES)


def test_records_without_a_use_case_are_listed(h: Harness, ledger: LedgerService) -> None:
    """001's quickstart row has no use case or content: listed under ``unscoped``, not skipped."""
    walk_to(h, "T1")
    with h.app.begin() as conn:
        conn.execute(
            text("INSERT INTO ledger.ledger_record (ledger_key, content_hash) VALUES ('qs/1', :h)"),
            {"h": "sha256:" + "0" * 64},
        )
    report = ledger.verify(AUDITOR, "all")
    assert report.verified and report.unscoped == ["qs/1"]
    assert report.records_checked == 1
    assert ledger.verify(AUDITOR, h.sql("SELECT usecase_id FROM run.usecase")[0][0]).unscoped == []
