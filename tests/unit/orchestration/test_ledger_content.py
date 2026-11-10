"""T012: baseline ledger record content and hash chain (research R-09, FR-027)."""

import hashlib
from typing import Any

from adlc.orchestration.ledger import build_record_content, make_record
from adlc.spec_toolkit.normalise import normalise


def _content(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "run_id": "UC-0001/T1/run-1",
        "usecase_id": "UC-0001",
        "terminal_id": "T1",
        "spec_version": "1.0.0",
        "spec_hash": "sha256:" + "a" * 64,
        "trigger": {"event_type": "T0.pass", "event_id": "e1"},
        "final_status": "pass",
        "decisions": [{"person": "p1", "role": "product_owner", "decision": "pass"}],
        "recommendation": {"status": "pass"},
        "artifacts": {"kpis": [{"kpi": "x"}]},
        "control_results": [{"id": "CTL-T1-01", "passed": True}],
        "clarifications": [{"clarification_id": "UC-0001/T1/run-1/clar-1"}],
        "waiver": None,
        "emitted": {"kpis": {"artifact": "kpis"}},
    }
    values.update(overrides)
    return build_record_content(**values)


def test_content_has_every_required_part() -> None:
    content = _content()
    assert set(content) == {
        "run_id",
        "usecase_id",
        "terminal_id",
        "spec",
        "trigger",
        "final_status",
        "decisions",
        "reviewer_recommendation",
        "artifacts",
        "control_results",
        "clarification_rounds",
        "waiver",
        "emitted",
    }
    assert content["spec"] == {"version": "1.0.0", "content_hash": "sha256:" + "a" * 64}


def test_hash_is_sha256_of_the_normal_form_and_ignores_key_order() -> None:
    content = _content()
    record = make_record(ledger_key="UC-0001/T1/run-1", content=content, previous_record_hash=None)
    expected = "sha256:" + hashlib.sha256(normalise(content).encode()).hexdigest()
    assert record.content_hash == expected
    reordered = dict(reversed(list(content.items())))
    again = make_record(ledger_key="k", content=reordered, previous_record_hash=None)
    assert again.content_hash == record.content_hash


def test_chain() -> None:
    first = make_record(ledger_key="a", content=_content(), previous_record_hash=None)
    second = make_record(
        ledger_key="b",
        content=_content(run_id="UC-0001/T2/run-1", terminal_id="T2"),
        previous_record_hash=first.content_hash,
    )
    assert first.previous_record_hash is None
    assert second.previous_record_hash == first.content_hash
    assert second.content_hash != first.content_hash
