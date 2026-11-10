"""T023: routing resolution over the real pinned specs (FR-009b, FR-014 to FR-020, R-05, R-06)."""

from typing import Any

import pytest

from adlc.orchestration import routing, spec_view
from adlc.spec_toolkit.registry import InMemorySpecRegistry


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ("usecase.submitted", ("T0",)),
        ("T0.pass", ("T1",)),
        ("T4.rework.implementation", ("T3",)),
        ("T8.event.drift", ("T9",)),
        ("T9.reentry.T2", ("T2",)),
        ("T8.terminate", ("T9",)),
        ("T1.rework.requirement", ()),  # self-route: reopened explicitly, not by subscription
        ("T7.escalate", ()),
    ],
)
def test_subscribers(pinned: dict[str, Any], event: str, expected: tuple[str, ...]) -> None:
    assert routing.subscribers(pinned, event) == expected


def test_subscribers_only_from_the_pinned_set(pinned: dict[str, Any]) -> None:
    without_t1 = {k: v for k, v in pinned.items() if k != "T1"}
    assert routing.subscribers(without_t1, "T0.pass") == ()


@pytest.mark.parametrize(
    ("status", "cause", "reentry", "expected"),
    [
        ("pass", None, None, "T4.pass"),
        ("exception", None, None, "T4.exception"),
        ("terminate", None, None, "T4.terminate"),
        ("rework", "implementation", None, "T4.rework.implementation"),
        ("pass", None, "T2", "T4.reentry.T2"),
    ],
)
def test_outcome_event_type(
    status: str, cause: str | None, reentry: str | None, expected: str
) -> None:
    assert routing.outcome_event_type("T4", status, cause, reentry) == expected


def test_event_kinds() -> None:
    assert routing.is_rework_event("T4.rework.implementation")
    assert not routing.is_rework_event("T4.pass")
    assert routing.is_terminate_event("T8.terminate")
    assert not routing.is_terminate_event("T8.event.terminate")
    assert routing.run_mode("T8.terminate") == "retire"
    assert routing.run_mode("T8.event.drift") == "evolve"
    assert routing.event_source("T8.event.drift") == "T8"


def test_rework_counter() -> None:
    history = ["T0.pass", "T1.rework.requirement", "T1.rework.requirement"]
    assert routing.rework_count(history, "T1.rework.requirement") == 3
    assert routing.rework_count(history, "T9.reentry.T1") == 2
    assert routing.over_rework_limit(4, 3)
    assert not routing.over_rework_limit(3, 3)


def test_destination_kinds_from_the_registry(registry: InMemorySpecRegistry) -> None:
    kinds = {
        ("T1", "pass", None): ("terminal", "T2"),
        ("T4", "rework", "implementation"): ("terminal", "T3"),
        ("T9", "pass", None): ("template", "${T9.change_impact_assessment.reentry_terminal}"),
        ("T8", "pass", None): ("special", "continue"),
        ("T6", "rework", "missing_evidence"): ("special", "owning_terminal"),
        ("T7", "exception", None): ("disabled", ""),
        ("T5", "escalate", None): ("special", "rai_board"),
    }
    for (terminal, status, cause), (kind, destination) in kinds.items():
        route = registry.outcome_route(terminal, status, cause)
        assert route is not None, (terminal, status)
        assert route.kind == kind, (terminal, status, route)
        if destination:
            assert route.destination == destination


def test_resolve_template() -> None:
    template = "${T9.change_impact_assessment.reentry_terminal}"
    artifacts = {"change_impact_assessment": [{"reentry_terminal": "T2"}]}
    assert routing.resolve_template(template, "T9", artifacts) == "T2"
    assert routing.resolve_template(template, "T8", artifacts) is None
    assert routing.resolve_template(template, "T9", {}) is None
    assert routing.is_template(template)


def test_template_must_name_a_reentry_terminal(pinned: dict[str, Any]) -> None:
    assert spec_view.reentry_terminals(pinned["T9"]) == {"T0", "T1", "T2", "T3"}


def test_emitted_values_need_the_owner_for_non_artifacts(pinned: dict[str, Any]) -> None:
    t0 = pinned["T0"]
    missing = routing.emitted_values(t0, {}, {"usecase_id": "UC-0001"}, {})
    assert missing.missing == ("risk_tier",)
    given = routing.emitted_values(t0, {}, {"usecase_id": "UC-0001"}, {"risk_tier": "high"})
    assert given.values == {"risk_tier": "high", "usecase_id": "UC-0001"}
    assert given.missing == ()


def test_emitted_values_reference_artifacts(pinned: dict[str, Any]) -> None:
    t1 = pinned["T1"]
    names = ("eval_thresholds", "rai_thresholds", "kpis", "autonomy_levels")
    artifacts = {n: [{"x": 1}] for n in names}
    result = routing.emitted_values(t1, artifacts, {}, {})
    assert result.missing == ()
    assert result.values["kpis"] == {"artifact": "kpis"}
    t3 = pinned["T3"]
    cells = {"candidate_package": [{"sha256": "abc"}], "build_manifest": [{}]}
    assert routing.emitted_values(t3, cells, {}, {}).values["candidate_package.sha256"] == "abc"


def test_sign_off_rule_selection(pinned: dict[str, Any]) -> None:
    plain = spec_view.sign_off_rule(pinned["T1"], "medium", "evolve")
    assert plain.roles == {"product_owner", "business_owner"}
    assert plain.min_approvers == 2
    low = spec_view.sign_off_rule(pinned["T5"], "low", "evolve")
    high = spec_view.sign_off_rule(pinned["T5"], "high", "evolve")
    assert low.roles == {"security_officer"}
    assert low.min_approvers == 1
    assert high.min_approvers == 4 and high.board == "rai_board"
    retire = spec_view.sign_off_rule(pinned["T9"], "medium", "retire")
    evolve = spec_view.sign_off_rule(pinned["T9"], "medium", "evolve")
    assert retire.roles == {"business_owner", "service_owner", "data_owner"}
    assert evolve.roles == {"product_owner"}
    t3 = spec_view.sign_off_rule(pinned["T3"], "medium", "evolve")
    assert [p.role for p in t3.plus] == ["solution_architect"]
    assert spec_view.sign_off_rule(pinned["T6"], "medium", "evolve").external == "cab"
