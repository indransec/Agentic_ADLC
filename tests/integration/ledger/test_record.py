"""T012: every closed run leaves a complete version-2 record (US1; FR-001 to FR-004)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from adlc.ledger import store as ledger_store
from adlc.ledger.content import record_hash
from adlc.ledger.storage import structured_hash
from adlc.orchestration import store as run_store
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person

KEYS = {
    "content_version",
    "run_id",
    "usecase_id",
    "terminal_id",
    "spec",
    "trigger",
    "final_status",
    "decisions",
    "reviewer_recommendation",
    "control_results",
    "clarification_rounds",
    "waiver",
    "emitted",
    "profile_version",
    "artifacts",
    "bound_to",
}


def _records(h: Harness, usecase: str) -> list[tuple[str, str, str | None, dict]]:  # type: ignore[type-arg]
    rows = h.sql(
        "SELECT ledger_key, content_hash, previous_record_hash, content_json FROM ledger.ledger_record "
        "WHERE usecase_id = :u ORDER BY ledger_record_id",
        u=usecase,
    )
    return [tuple(r) for r in rows]  # type: ignore[misc]


def test_record_contents_and_artifact_hashes(h: Harness) -> None:
    usecase, t2 = walk_to(h, "T2")
    records = _records(h, usecase)
    assert len(records) == 2
    key, digest, previous, content = records[1]  # T1
    assert set(content) == KEYS and content["content_version"] == 2
    assert digest == record_hash(content)
    assert previous == records[0][1]
    assert [a["id"] for a in content["artifacts"]][:3] == [
        "functional_requirements",
        "non_functional_requirements",
        "behavioural_requirements",
    ]
    with h.app.connect() as conn:
        for artifact in content["artifacts"]:
            body = ledger_store.load_blob(conn, artifact["content_hash"])
            assert body is not None and structured_hash(body) == artifact["content_hash"]
            assert artifact["producer"]["type"] == "agent" and artifact["version"] == 1
    assert content["emitted"]["kpis"]["artifact"] == "kpis"
    assert content["emitted"]["kpis"]["content_hash"].startswith("sha256:")


def test_package_binding_from_t4(h: Harness) -> None:
    usecase, t5 = walk_to(h, "T5")
    t4 = [r for r in _records(h, usecase) if r[0].endswith("/T4/run-1")][0][3]
    package = h.agent.base["T3"]["candidate_package"][0]["sha256"]
    assert t4["bound_to"] == package
    t1 = [r for r in _records(h, usecase) if r[0].endswith("/T1/run-1")][0][3]
    assert t1["bound_to"] is None


def test_close_is_atomic_with_the_record(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    usecase, t0 = walk_to(h, "T0")

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("crash after the record")

    monkeypatch.setattr(run_store, "insert_event", boom)
    with pytest.raises(RuntimeError):
        h.service.decide(person("business_owner"), t0, "pass", fields={"risk_tier": "low"})
    assert _records(h, usecase) == []


def test_records_and_content_are_immutable(h: Harness) -> None:
    walk_to(h, "T1")
    for engine in (h.app, h.owner):
        with engine.connect() as conn:
            for sql in (
                "UPDATE ledger.ledger_record SET content_json = '{}'",
                "DELETE FROM ledger.ledger_record",
                "UPDATE ledger.content_blob SET size = 1",
                "DELETE FROM ledger.content_blob",
            ):
                with pytest.raises(DBAPIError), conn.begin_nested():
                    conn.execute(text(sql))
