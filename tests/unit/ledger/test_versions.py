"""T015: version rules (FR-008, FR-010)."""

from adlc.ledger.artifacts import changed, enrich_emitted, schema_valid
from adlc.ledger.storage import structured_hash


def test_schema_valid() -> None:
    assert schema_valid([{"a": 1, "b": None}], ("a", "b"))
    assert not schema_valid([{"a": 1}], ("a", "b"))
    assert not schema_valid({"a": 1}, ("a",))
    assert not schema_valid([1, 2], ("a",))
    assert schema_valid([], ("a",))  # an empty table has no row missing a column


def test_changed_uses_the_normal_form() -> None:
    rows = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    digest = structured_hash(rows)
    assert not changed(digest, [{"b": 2, "a": 1}, {"b": 4, "a": 3}])  # key order
    assert changed(digest, list(reversed(rows)))  # row order
    assert changed(None, rows)


def test_emitted_references_carry_version_and_hash() -> None:
    entries = [{"id": "kpis", "version": 2, "content_hash": "sha256:x"}]
    emitted = {"kpis": {"artifact": "kpis"}, "risk_tier": "high"}
    assert enrich_emitted(emitted, entries) == {
        "kpis": {"artifact": "kpis", "version": 2, "content_hash": "sha256:x"},
        "risk_tier": "high",
    }
