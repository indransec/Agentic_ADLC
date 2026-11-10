"""T025: verification rules over in-memory records (contracts/verification.md)."""

from typing import Any

from adlc.ledger.content import build_v2, record_hash
from adlc.ledger.storage import file_hash, structured_hash
from adlc.ledger.verify import RecordRow, check_chain

PACKAGE = [{"package_uri": "u", "sha256": "sha256:pkg"}]
NOTE = b"notes"
BOUND_SPEC = {"terminal": {"evidence": {"ledger": {"bound_to": "T3.candidate_package.sha256"}}}}


def _v2(
    run: str, terminal: str, artifacts: list[dict[str, Any]], bound_to: Any = None
) -> dict[str, Any]:
    return build_v2(
        run_id=run,
        usecase_id="UC-0001",
        terminal_id=terminal,
        spec_version="1.0.0",
        spec_hash="sha256:s",
        trigger={},
        final_status="pass",
        decisions=[],
        recommendation=None,
        control_results=[],
        clarifications=[],
        waiver=None,
        emitted={},
        profile_version=0,
        artifacts=artifacts,
        bound_to=bound_to,
    )


def _chain(contents: list[dict[str, Any]]) -> list[RecordRow]:
    rows: list[RecordRow] = []
    previous = None
    for i, content in enumerate(contents):
        digest = record_hash(content)
        rows.append(RecordRow(f"key-{i}", "UC-0001", digest, previous, content))
        previous = digest
    return rows


BLOBS = {structured_hash(PACKAGE): PACKAGE}
FILES = {file_hash(NOTE): NOTE}


def _check(
    rows: list[RecordRow], blobs: dict[str, Any] = BLOBS, files: dict[str, bytes] = FILES
) -> list[Any]:
    return check_chain(rows, blobs.get, files.get, lambda t, v: BOUND_SPEC if t == "T4" else {})


def _healthy() -> list[RecordRow]:
    t3 = _v2(
        "r3",
        "T3",
        [
            {
                "id": "candidate_package",
                "content_hash": structured_hash(PACKAGE),
                "attachments": [{"content_hash": file_hash(NOTE), "name": "n.md"}],
            }
        ],
    )
    t4 = _v2("r4", "T4", [], bound_to="sha256:pkg")
    return _chain([{"run_id": "r0", "artifacts": {"x": [1]}}, t3, t4])  # a version-1 record first


def test_clean_chain() -> None:
    assert _check(_healthy()) == []


def test_content_break() -> None:
    rows = _healthy()
    rows[1] = RecordRow(
        rows[1].ledger_key,
        "UC-0001",
        rows[1].content_hash,
        rows[1].previous_record_hash,
        {**rows[1].content, "final_status": "rework"},
    )
    breaks = _check(rows)
    assert [(b.ledger_key, b.check) for b in breaks] == [("key-1", "content")]


def test_chain_break() -> None:
    rows = _healthy()
    rows[2] = RecordRow(
        rows[2].ledger_key, "UC-0001", rows[2].content_hash, "sha256:other", rows[2].content
    )
    assert [(b.check, b.element) for b in _check(rows)] == [("chain", "previous_record_hash")]


def test_artifact_and_attachment_breaks() -> None:
    tampered = {structured_hash(PACKAGE): [{"package_uri": "u", "sha256": "sha256:evil"}]}
    breaks = _check(_healthy(), blobs=tampered, files={})
    checks = {(b.check, b.element) for b in breaks}
    assert ("artifact", "candidate_package") in checks
    assert ("attachment", "candidate_package/n.md") in checks
    assert all("evil" not in str(b) or b.check == "binding" for b in breaks)


def test_binding_break() -> None:
    rows = _healthy()
    t4 = _v2("r4", "T4", [], bound_to="sha256:different")
    rows[2] = _chain([dict(rows[0].content), dict(rows[1].content), t4])[2]
    breaks = _check(rows)
    assert [(b.check, b.expected, b.actual) for b in breaks] == [
        ("binding", "sha256:pkg", "sha256:different")
    ]


def test_version_one_checks_hash_and_chain_only() -> None:
    rows = _chain([{"run_id": "r0", "artifacts": {"x": [{"no": "hashes"}]}}])
    assert _check(rows, blobs={}, files={}) == []
