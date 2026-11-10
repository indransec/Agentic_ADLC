"""T007: ledger record content version 2 (contracts/record.md)."""

from typing import Any

from adlc.ledger.content import CONTENT_VERSION, build_v2, content_version, record_hash

ARTIFACT = {
    "id": "kpis",
    "version": 2,
    "content_hash": "sha256:" + "a" * 64,
    "schema_valid": True,
    "producer": {"type": "person", "id": "owner"},
    "attachments": [],
}


def _content(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "run_id": "UC-0001/T1/run-2",
        "usecase_id": "UC-0001",
        "terminal_id": "T1",
        "spec_version": "1.0.0",
        "spec_hash": "sha256:" + "b" * 64,
        "trigger": {"event_type": "T0.pass", "event_id": None, "context": {}},
        "final_status": "pass",
        "decisions": [],
        "recommendation": None,
        "control_results": [],
        "clarifications": [],
        "waiver": None,
        "emitted": {},
        "profile_version": 1,
        "artifacts": [ARTIFACT],
        "bound_to": None,
    }
    values.update(overrides)
    return build_v2(**values)


def test_keys_and_nulls() -> None:
    content = _content()
    assert set(content) == {
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
    assert content["content_version"] == CONTENT_VERSION == 2
    assert content["bound_to"] is None and content["waiver"] is None
    assert content["artifacts"] == [ARTIFACT]


def test_hash_stability() -> None:
    content = _content()
    assert record_hash(content) == record_hash(dict(reversed(list(content.items()))))
    other = _content(artifacts=[{**ARTIFACT, "content_hash": "sha256:" + "c" * 64}])
    assert record_hash(other) != record_hash(content)


def test_content_version() -> None:
    assert content_version(_content()) == 2
    assert content_version({"run_id": "x", "artifacts": {}}) == 1
