"""T026: pass sign-off rules (FR-009, FR-009b, FR-011, FR-018a; US2/AC3, AC5)."""

import pytest

from adlc.orchestration.service import Actor, InvalidDecision, NotAuthorised
from adlc.orchestration.stubs import StubAgent, StubPolicy
from tests.support.orchestration import Harness, harness, person
from tests.support.pg import PlatformDatabase


def _to(h: Harness, terminal: str) -> tuple[str, str]:
    usecase = h.submit()
    order = ["T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]
    for t in order[: order.index(terminal)]:
        h.pass_run(h.active(usecase, t).run_id, {"risk_tier": "medium"})
    return usecase, h.active(usecase, terminal).run_id


def test_non_holder_is_refused(h: Harness) -> None:
    _, run_id = _to(h, "T0")
    with pytest.raises(NotAuthorised):
        h.service.decide(person("sre"), run_id, "pass", fields={"risk_tier": "low"})
    with pytest.raises(NotAuthorised):
        h.service.decide(Actor.system("bot"), run_id, "pass", fields={"risk_tier": "low"})


def test_two_approvers_needed(h: Harness) -> None:
    _, run_id = _to(h, "T1")  # sign_off: product_owner + business_owner, min 2
    h.service.decide(person("product_owner"), run_id, "pass")
    h.service.decide(person("product_owner"), run_id, "pass")  # same person counts once
    assert h.run(run_id).state == "awaiting_sign_off"
    h.service.decide(person("business_owner"), run_id, "pass")
    assert h.run(run_id).final_status == "pass"


def test_plus_approver_needed_in_addition(orch_template: PlatformDatabase) -> None:
    # engineering_lead min 1, plus solution_architect when the build deviates from the design
    deviation = {"design_conformance": {"deviation": "caching layer added"}}
    with harness(orch_template, agent=StubAgent({"T3": {1: deviation}})) as h:
        _, run_id = _to(h, "T3")
        h.service.decide(person("engineering_lead"), run_id, "pass")
        assert h.run(run_id).state == "awaiting_sign_off"
        h.service.decide(person("solution_architect"), run_id, "pass")
        assert h.run(run_id).final_status == "pass"


def test_plus_not_needed_without_deviation(h: Harness) -> None:
    _, run_id = _to(h, "T3")  # the synthetic T3 build has no design deviation
    h.service.decide(person("engineering_lead"), run_id, "pass")
    assert h.run(run_id).final_status == "pass"


def test_plus_not_needed_when_condition_false(orch_template: PlatformDatabase) -> None:
    policy = StubPolicy({("T3", "plus:solution_architect"): False})
    with harness(orch_template, policy=policy) as h:
        _, run_id = _to(h, "T3")
        h.service.decide(person("engineering_lead"), run_id, "pass")
        assert h.run(run_id).final_status == "pass"


def test_emitted_value_required(h: Harness) -> None:
    usecase, run_id = _to(h, "T0")
    with pytest.raises(InvalidDecision, match="risk_tier"):
        h.service.decide(person("business_owner"), run_id, "pass")
    h.service.decide(person("business_owner"), run_id, "pass", fields={"risk_tier": "high"})
    assert h.service.get_usecase(usecase).risk_tier == "high"
    payload = h.sql("SELECT payload FROM events.outbox_event WHERE event_type = 'T0.pass'")[0][0]
    assert payload["ledger_key"] == run_id
    assert payload["status"] == "pass"
    assert payload["emits"] == {"risk_tier": "high", "usecase_id": usecase}


def test_tier_drives_timers_and_rules(h: Harness) -> None:
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "high"})
    t1 = h.active(usecase, "T1")
    assert t1.due_at is not None and (t1.due_at - t1.opened_at).days == 8  # high: 8d
