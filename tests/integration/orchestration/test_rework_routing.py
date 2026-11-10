"""T037: rework routing by root cause and evidence for the next run (FR-010, FR-015, FR-019; US2/AC2)."""

import pytest

from adlc.orchestration.service import InvalidDecision
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person


def test_root_cause_routes_and_carries_evidence(h: Harness) -> None:
    usecase, run_id = walk_to(h, "T4")
    h.service.decide(
        person("qa_eval_lead"),
        run_id,
        "rework",
        comment="Tool timeout on claim lookup",
        root_cause="implementation",
        reason="eval failures",
        fields={"defect_log": "DEF-7 claim lookup times out"},
    )
    h.drain()
    event = h.sql(
        "SELECT event_type, payload FROM events.outbox_event WHERE causation_run_id = :r", r=run_id
    )
    assert event[0][0] == "T4.rework.implementation"
    t3 = h.active(usecase, "T3")
    assert t3.run_id == f"{usecase}/T3/run-2"
    assert t3.rework_count == 1
    assert t3.trigger_context["comment"] == "Tool timeout on claim lookup"
    assert t3.trigger_context["root_cause"] == "implementation"
    assert t3.trigger_context["causing_run_id"] == run_id
    assert t3.trigger_context["ledger_key"] == run_id
    assert t3.trigger_context["decision_fields"] == {"defect_log": "DEF-7 claim lookup times out"}
    build = [c for c in h.agent.contexts if c.run_id == t3.run_id][0]
    assert build.trigger["comment"] == "Tool timeout on claim lookup"
    assert build.previous_artifacts  # T3 run 1's artifacts


def test_self_route_reopens_the_same_terminal(h: Harness) -> None:
    usecase, run_id = walk_to(h, "T1")
    h.service.decide(
        person("product_owner"),
        run_id,
        "rework",
        comment="KPI missing",
        root_cause="requirement",
        reason="r",
    )
    h.drain()
    run2 = h.active(usecase, "T1")
    assert (run2.run_number, run2.rework_count, run2.trigger_event_type) == (
        2,
        1,
        "T1.rework.requirement",
    )


def test_owning_terminal_resolver(h: Harness) -> None:
    usecase, run_id = walk_to(h, "T6")
    rm = person("release_manager")
    with pytest.raises(InvalidDecision, match="owning terminal"):
        h.service.decide(
            rm,
            run_id,
            "rework",
            comment="c",
            root_cause="missing_evidence",
            reason="r",
            fields={"gap_list": "x"},
        )
    h.service.decide(
        rm,
        run_id,
        "rework",
        comment="no pen test",
        root_cause="missing_evidence",
        reason="r",
        fields={"gap_list": "pen test"},
        target_terminal="T5",
    )
    h.drain()
    t5 = h.active(usecase, "T5")
    assert (t5.run_number, t5.trigger_event_type, t5.rework_count) == (
        2,
        "T6.rework.missing_evidence",
        1,
    )
