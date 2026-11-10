"""T040: sign-off rule by tier and by mode; boards and external bodies are recorded only (FR-009b, FR-009c)."""

from adlc.orchestration.stubs import StubPolicy
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, harness, person
from tests.support.pg import PlatformDatabase


def test_by_tier(h: Harness) -> None:
    _, low = walk_to(h, "T5", tier="low")
    h.service.decide(person("security_officer"), low, "pass")
    assert h.run(low).final_status == "pass"  # low: one approver


def test_by_tier_high_needs_four(h: Harness) -> None:
    _, run_id = walk_to(h, "T5", tier="high")
    for role in ("security_officer", "privacy_officer", "rai_officer"):
        h.service.decide(person(role), run_id, "pass")
        assert h.run(run_id).state == "awaiting_sign_off"
    h.service.decide(person("compliance_officer"), run_id, "pass")  # board is notification only
    assert h.run(run_id).final_status == "pass"


def test_by_mode_retire(h: Harness) -> None:
    usecase, t8 = walk_to(h, "T8")
    h.service.decide(person("business_owner"), t8, "terminate", comment="retire")
    h.drain()
    t9 = h.active(usecase, "T9").run_id
    h.service.decide(
        person("business_owner"), t9, "pass", fields={"alternative": "lifecycle_closed"}
    )
    assert h.run(t9).state == "awaiting_sign_off"  # retire: three approvers
    h.service.decide(
        person("service_owner"), t9, "pass", fields={"alternative": "lifecycle_closed"}
    )
    h.service.decide(person("data_owner"), t9, "pass", fields={"alternative": "lifecycle_closed"})
    h.drain()
    assert h.run(t9).final_status == "pass"
    assert h.service.get_usecase(usecase).status == "closed"


def test_external_body_does_not_block(h: Harness) -> None:
    _, run_id = walk_to(h, "T6")
    for role in ("release_manager", "service_owner", "business_owner"):
        h.service.decide(person(role), run_id, "pass", fields={"release_authorisation": "x"})
    assert h.run(run_id).final_status == "pass"


def _notified(h: Harness, run_id: str) -> list[object]:
    return [
        r[0]["bodies"]
        for r in h.sql(
            "SELECT detail FROM run.run_activity WHERE run_id = :r AND outcome = 'notified'",
            r=run_id,
        )
    ]


def test_board_and_external_bodies_are_notified(h: Harness) -> None:
    """FR-009c (T077): recorded as notifications on close, never as gates."""
    _, t5 = walk_to(h, "T5", tier="high")
    h.pass_run(t5)
    assert _notified(h, t5) == [["rai_board"]]
    payload = h.sql("SELECT payload FROM events.outbox_event WHERE causation_run_id = :r", r=t5)
    assert payload[0][0]["notify_bodies"] == ["rai_board"]
    t6 = h.active(h.run(t5).usecase_id, "T6").run_id
    h.pass_run(t6)
    assert _notified(h, t6) == [["cab"]]


def test_external_body_only_when_its_condition_holds(orch_template: PlatformDatabase) -> None:
    policy = StubPolicy({("T6", "external:cab"): False})
    with harness(orch_template, policy=policy) as h:
        _, t6 = walk_to(h, "T6")
        h.pass_run(t6)
        assert _notified(h, t6) == []
