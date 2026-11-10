"""T024: submit pins every active spec and opens T0 (FR-001, FR-002, US1/AC1)."""

import pytest
from sqlalchemy import text

from adlc.orchestration.service import Actor, InvalidDecision, NoActiveSpecs, NotAuthorised
from tests.support.orchestration import Harness, person

ALL = [f"T{n}" for n in range(10)]


def test_submit_pins_and_opens_t0(h: Harness) -> None:
    usecase = h.submit("Claims triage")
    assert usecase == "UC-0001"
    record = h.service.get_usecase(usecase)
    assert (record.business_owner, record.status, record.risk_tier) == (
        "business_owner-person",
        "active",
        None,
    )
    pins = h.sql(
        "SELECT terminal_id, version FROM spec.usecase_spec_pin WHERE usecase_id = :u ORDER BY terminal_id",
        u=usecase,
    )
    assert [p[0] for p in pins] == ALL
    runs = h.runs(usecase)
    assert [(r.run_id, r.mode, r.trigger_event_type) for r in runs] == [
        ("UC-0001/T0/run-1", "evolve", "usecase.submitted")
    ]
    assert h.submit() == "UC-0002"


def test_submit_validates(h: Harness) -> None:
    with pytest.raises(InvalidDecision):
        h.service.submit_usecase(person("business_owner"), " ", "intake")
    with pytest.raises(NotAuthorised):
        h.service.submit_usecase(Actor.system("bot"), "x", "intake")


def test_no_active_specs(h: Harness) -> None:
    with h.owner.begin() as conn:
        conn.execute(text("UPDATE spec.spec_registry SET status = 'deprecated'"))
    with pytest.raises(NoActiveSpecs):
        h.service.submit_usecase(person("business_owner"), "x", "intake")


def test_pinned_version_survives_a_new_registration(h: Harness) -> None:
    """Spec Edge Cases: a use case keeps its pinned versions (C1)."""
    usecase = h.submit()
    with h.owner.begin() as conn:
        conn.execute(
            text(
                "UPDATE spec.spec_registry SET status = 'deprecated', deprecated_at = now() "
                "WHERE terminal_id = 'T1'"
            )
        )
        conn.execute(
            text(
                "INSERT INTO spec.spec_registry (terminal_id, version, status, schema_version, "
                "spec_yaml, spec_json, content_hash, trigger_events, emitted_events) "
                "SELECT terminal_id, '1.1.0', 'active', schema_version, spec_yaml, spec_json, "
                "content_hash, trigger_events, emitted_events FROM spec.spec_registry "
                "WHERE terminal_id = 'T1'"
            )
        )
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "low"})
    assert h.active(usecase, "T1").spec_version == "1.0.0"
