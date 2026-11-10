"""T036: decision validation (FR-009a, FR-010, FR-012; US2/AC1, AC4, AC5; spec Edge Cases)."""

import threading

import pytest

from adlc.orchestration.engine import StaleRun
from adlc.orchestration.interfaces import Recommendation
from adlc.orchestration.service import InvalidDecision, NotAuthorised
from adlc.orchestration.stubs import StubReviewer
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, harness, person
from tests.support.pg import PlatformDatabase

PO = person("product_owner")


def _writes(h: Harness) -> tuple[int, int]:
    return (
        h.sql("SELECT count(*) FROM run.sign_off")[0][0],
        h.sql("SELECT count(*) FROM events.outbox_event")[0][0],
    )


def test_rework_needs_comment_and_cause(h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    before = _writes(h)
    with pytest.raises(InvalidDecision, match="comment and a root cause"):
        h.service.decide(PO, run_id, "rework", root_cause="requirement", reason="r")
    with pytest.raises(InvalidDecision, match="comment and a root cause"):
        h.service.decide(PO, run_id, "rework", comment="missing KPI", reason="r")
    with pytest.raises(InvalidDecision, match="not routed; allowed: requirement, qualification"):
        h.service.decide(PO, run_id, "rework", comment="c", root_cause="defect", reason="r")
    assert _writes(h) == before


def test_rework_extra_required_fields(h: Harness) -> None:
    _, run_id = walk_to(h, "T5")  # rework requires findings
    with pytest.raises(InvalidDecision, match="findings"):
        h.service.decide(
            person("security_officer"),
            run_id,
            "rework",
            comment="c",
            root_cause="architecture",
            reason="r",
        )


def test_differing_decision_needs_reason(h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    with pytest.raises(InvalidDecision, match="reviewer recommended pass"):
        h.service.decide(PO, run_id, "rework", comment="c", root_cause="requirement")
    h.service.decide(PO, run_id, "rework", comment="c", root_cause="requirement", reason="KPI gap")
    assert h.run(run_id).final_status == "rework"


def test_matching_recommendation_needs_no_reason(orch_template: PlatformDatabase) -> None:
    reviewer = StubReviewer({"T1": {1: Recommendation("rework")}})
    with harness(orch_template, reviewer=reviewer) as h:
        _, run_id = walk_to(h, "T1")
        h.service.decide(PO, run_id, "rework", comment="c", root_cause="requirement")
        assert h.run(run_id).final_status == "rework"


def test_non_holder_refused(h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    with pytest.raises(NotAuthorised):
        h.service.decide(
            person("sre"), run_id, "rework", comment="c", root_cause="requirement", reason="r"
        )


def test_terminate_rules(h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    with pytest.raises(NotAuthorised):  # terminate is set_by business_owner
        h.service.decide(PO, run_id, "terminate", comment="stop")
    with pytest.raises(InvalidDecision, match="reason"):
        h.service.decide(person("business_owner"), run_id, "terminate")
    h.service.decide(person("business_owner"), run_id, "terminate", comment="no business case")
    assert h.run(run_id).final_status == "terminate"


def test_not_allowed_outcome(h: Harness) -> None:
    _, run_id = walk_to(h, "T7")  # exception: not_allowed
    with pytest.raises(InvalidDecision, match="not allowed"):
        h.service.decide(
            person("release_manager"),
            run_id,
            "exception",
            reason="r",
            fields={"expiry": "2099-01-01"},
        )


def test_unknown_decision(h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    with pytest.raises(InvalidDecision):
        h.service.decide(PO, run_id, "escalate", reason="r")


def test_concurrent_decisions_one_wins(h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    version = h.run(run_id).version
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def decide() -> None:
        barrier.wait()
        try:
            h.service.decide(
                PO,
                run_id,
                "rework",
                comment="c",
                root_cause="requirement",
                reason="r",
                expected_version=version,
            )
            outcomes.append("won")
        except StaleRun:
            outcomes.append("stale")

    threads = [threading.Thread(target=decide) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["stale", "won"]
    assert h.sql("SELECT count(*) FROM run.sign_off WHERE run_id = :r", r=run_id)[0][0] == 1
