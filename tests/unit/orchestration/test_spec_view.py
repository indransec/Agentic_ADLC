"""Spec accessors over the real specs, including the clarification addressee (T051, FR-023a)."""

from typing import Any

import pytest

from adlc.orchestration import spec_view


def test_addressee_rule_is_generic(pinned: dict[str, Any]) -> None:
    for spec in pinned.values():
        roles = spec_view.human_roles(spec)
        r_roles = [r.role for r in roles if r.raci == "R"]
        whole_a = [r.role for r in roles if r.raci == "A" and r.scope is None]
        any_a = [r.role for r in roles if r.raci == "A"]
        candidates: list[str | None] = [*(r_roles or whole_a or any_a), None]
        expected = candidates[0]
        assert spec_view.default_addressee(spec) == expected


def test_addressee_examples(pinned: dict[str, Any]) -> None:
    assert spec_view.default_addressee(pinned["T1"]) == "business_owner"  # the R role
    assert spec_view.default_addressee(pinned["T9"]) == "service_owner"  # R before scoped A roles


def test_addressee_falls_back_to_scoped_a() -> None:
    spec: dict[str, Any] = {
        "terminal": {
            "metadata": {"id": "T99"},
            "actors": {
                "human_roles": [
                    {"role": "x", "raci": "C"},
                    {"role": "evolver", "raci": "A", "scope": "evolve"},
                    {"role": "retirer", "raci": "A", "scope": "retire"},
                ]
            },
        }
    }
    assert spec_view.default_addressee(spec) == "evolver"
    spec["terminal"]["actors"]["human_roles"].append({"role": "owner", "raci": "A"})
    assert spec_view.default_addressee(spec) == "owner"


def test_accessors(pinned: dict[str, Any]) -> None:
    t1 = pinned["T1"]
    assert spec_view.terminal_id(t1) == "T1"
    assert [c.id for c in spec_view.prerequisites(t1)] == ["PRE-T1-01", "PRE-T1-02", "PRE-T1-03"]
    assert all(c.blocking for c in spec_view.controls(t1))
    assert spec_view.checklist_items(t1)[0] == "CHK-T1-01"
    assert spec_view.ledger_key(t1, "UC-0001", "run-2") == "UC-0001/T1/run-2"
    assert spec_view.ledger_key(pinned["T8"], "UC-0001", "run-3") == "UC-0001/T8/run-3"
    odd = {"terminal": {"evidence": {"ledger": {"key": "${usecase_id}/${unknown}"}}}}
    with pytest.raises(ValueError, match="unresolved"):
        spec_view.ledger_key(odd, "UC-0001", "run-1")
    assert spec_view.rework_causes(t1) == ("requirement", "qualification")
    assert spec_view.outcome_requires(pinned["T5"], "exception") == (
        "risk_acceptance",
        "expiry",
        "compensating_control",
    )
    assert spec_view.outcome_set_by(pinned["T5"], "exception") == {"risk_owner"}
    assert spec_view.outcome_not_allowed(pinned["T7"], "exception")
    assert "T8.event.drift" in spec_view.raised_events(pinned["T8"])
    assert spec_view.review_schedule(pinned["T8"], "high") == "weekly"
    assert spec_view.trigger_mode(pinned["T8"]) == "continuous"
    assert spec_view.status_rights(pinned["T8"], "agent") == {"raise_event"}
    conditional = [a for a in spec_view.artifacts(pinned["T9"]) if a.condition]
    assert conditional and all("retire" in (a.condition or "") for a in conditional)
