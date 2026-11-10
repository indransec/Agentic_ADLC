"""T040: sign-off rule by tier and by mode; boards and external bodies are recorded only (FR-009b, FR-009c)."""

from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person


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
