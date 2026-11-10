"""T055: spec → projection rows (pure; data-model.md projection tables)."""

from pathlib import Path

import pytest

from adlc.spec_toolkit.catalogues import Catalogues
from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.projections import Projection, project
from adlc.spec_toolkit.rules.single_spec import spec

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def projections() -> dict[str, Projection]:
    bundle = load_bundle(ROOT / "adlc-specs")
    cats = Catalogues.from_bundle(bundle)
    known = {spec(t)["metadata"]["id"] for t in bundle.terminals.values()}
    return {
        spec(t)["metadata"]["id"]: project(spec(t), cats, known) for t in bundle.terminals.values()
    }


def _route(p: Projection, status: str, cause: str | None = None):  # type: ignore[no-untyped-def]
    matches = [r for r in p.outcome_routes if r.outcome_status == status and r.root_cause == cause]
    assert len(matches) == 1, (status, cause, p.outcome_routes)
    return matches[0]


def test_triggers(projections: dict[str, Projection]) -> None:
    assert projections["T0"].triggers == (
        "usecase.submitted",
        "T9.reentry.T0",
        "T1.rework.qualification",
    )


def test_root_cause_routes(projections: dict[str, Projection]) -> None:
    route = _route(projections["T4"], "rework", "implementation")
    assert (route.destination_kind, route.destination) == ("terminal", "T3")
    assert route.requires == ("defect_log",)
    assert _route(projections["T6"], "rework", "missing_evidence").destination_kind == "special"


def test_exception_route_details(projections: dict[str, Projection]) -> None:
    route = _route(projections["T5"], "exception")
    assert route.destination == "T6"
    assert route.recheck_at == ("T6", "T8")
    assert route.set_by == ("risk_owner",)


def test_disabled_and_terminating(projections: dict[str, Projection]) -> None:
    assert _route(projections["T7"], "exception").destination_kind == "disabled"
    assert _route(projections["T0"], "terminate").destination_kind == "terminating"
    assert _route(projections["T0"], "terminate").notify == ("adlc_coe",)


def test_template_and_alternatives(projections: dict[str, Projection]) -> None:
    route = _route(projections["T9"], "pass")
    assert route.destination_kind == "template"
    assert route.alternatives == ("lifecycle_closed",)


def test_escalate_condition_and_notify(projections: dict[str, Projection]) -> None:
    route = _route(projections["T6"], "escalate")
    assert (route.destination_kind, route.destination) == ("special", "release_board")
    assert route.notify == ("business_owner",)
    assert route.condition and "go_no_go_disputed" in route.condition


def test_event_routes(projections: dict[str, Projection]) -> None:
    routes = {r.event_type: r for r in projections["T8"].event_routes}
    assert routes["T8.event.drift"].destination == "T9"
    breach = routes["T8.event.safety_breach"]
    assert (breach.destination, breach.immediate) == ("T5", ("reduce_autonomy_or_kill_switch",))
    incident = routes["T8.event.incident"]
    assert (incident.destination_kind, incident.then_destination) == ("special", "T7.rollback")
    assert incident.condition == 'trigger.severity == "sev1"'


def test_change_classes(projections: dict[str, Projection]) -> None:
    classes = {c.change_class: c for c in projections["T9"].change_classes}
    assert classes["moderate"].reentry_terminal == "T2"
    assert classes["major"].path == ("full",)
    assert classes["emergency"].retrospective == ("T4", "T5")
    assert classes["emergency"].within == "5d"
    assert classes["strategic"].alternative == "lifecycle_closed"


def test_timelines(projections: dict[str, Projection]) -> None:
    t3 = {t.risk_tier: t for t in projections["T3"].timelines}
    assert set(t3) == {"low", "medium", "high"}
    assert t3["medium"].expected_duration == "10d"
    assert (t3["high"].reminder_after, t3["high"].max_rework_cycles) == ("5d", 3)
    assert t3["low"].max_clarification_rounds == 2
    t7 = {t.risk_tier: t for t in projections["T7"].timelines}
    assert t7["low"].escalate_after is None and t7["low"].escalate_at_window_end
    t8 = {t.risk_tier: t for t in projections["T8"].timelines}
    assert t8["medium"].continuous and t8["medium"].expected_duration is None
    t9 = {t.risk_tier: t for t in projections["T9"].timelines}
    assert t9["high"].retirement_duration == "20d"


def test_emitted_events(projections: dict[str, Projection]) -> None:
    assert {"T7.rollback", "T7.rework.defect", "T7.pass"} <= set(projections["T7"].emitted_events)
    assert "T7.exception" not in projections["T7"].emitted_events
    assert "T9.reentry.T2" in projections["T9"].emitted_events
