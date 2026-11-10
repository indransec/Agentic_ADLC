"""T021: profile merge rules (FR-013, FR-015)."""

from typing import Any

from adlc.ledger.profile import merge, proposed_parameter


def test_merge_replaces_by_name_and_keeps_others() -> None:
    v1: dict[str, Any] = {
        "risk_tier": "medium",
        "kpis": {"artifact": "kpis", "version": 1, "content_hash": "sha256:a"},
    }
    v2 = merge(
        v1,
        {
            "kpis": {"artifact": "kpis", "version": 2, "content_hash": "sha256:b"},
            "token_budget": 0.04,
        },
    )
    assert v2 == {
        "risk_tier": "medium",
        "kpis": {"artifact": "kpis", "version": 2, "content_hash": "sha256:b"},
        "token_budget": 0.04,
    }
    assert v1["kpis"]["version"] == 1  # the previous version is not changed


def test_tables_are_replaced_whole() -> None:
    previous = {"thresholds": [{"m": "a"}, {"m": "b"}]}
    assert merge(previous, {"thresholds": [{"m": "c"}]}) == {"thresholds": [{"m": "c"}]}


def test_proposed_parameter() -> None:
    assert proposed_parameter(2) == 2
    assert proposed_parameter({"value": 0.01, "note": "stricter"}) == 0.01
    assert proposed_parameter({"artifact": "kpis"}) == {"artifact": "kpis"}
