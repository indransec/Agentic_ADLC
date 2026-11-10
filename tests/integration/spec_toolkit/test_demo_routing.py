"""T061: the demo routing table (contracts/spec-registry-interface.md) from both registries (SC-007)."""

from pathlib import Path

import pytest
from sqlalchemy import Engine

from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.register import register
from adlc.spec_toolkit.registry import InMemorySpecRegistry, SpecRegistry, SqlSpecRegistry

ROOT = Path(__file__).resolve().parents[3]
SPECS = ROOT / "adlc-specs"


@pytest.fixture
def registries(owner_engine: Engine, app_engine: Engine) -> list[SpecRegistry]:
    register(SPECS, owner_engine)
    return [SqlSpecRegistry(app_engine), InMemorySpecRegistry.from_bundle(load_bundle(SPECS))]


def test_start(registries: list[SpecRegistry]) -> None:
    for reg in registries:
        assert [t.terminal_id for t in reg.terminals_opened_by("usecase.submitted")] == ["T0"]


def test_d2_rework_with_comment(registries: list[SpecRegistry]) -> None:
    for reg in registries:
        route = reg.outcome_route("T1", "rework", "requirement")
        assert route is not None
        assert (route.kind, route.destination, route.requires) == (
            "terminal",
            "T1",
            ("owner_comment",),
        )


def test_d3_root_cause_routing(registries: list[SpecRegistry]) -> None:
    for reg in registries:
        route = reg.outcome_route("T4", "rework", "implementation")
        assert route is not None and (route.destination, route.requires) == ("T3", ("defect_log",))
        assert [t.terminal_id for t in reg.terminals_opened_by("T4.rework.implementation")] == [
            "T3"
        ]


def test_d4_escalation(registries: list[SpecRegistry]) -> None:
    for reg in registries:
        timeline = reg.timeline("T1", "medium")
        assert timeline is not None and timeline.max_rework_cycles == 3
        route = reg.outcome_route("T1", "escalate")
        assert route is not None and (route.kind, route.destination) == (
            "special",
            "human_completion",
        )


def test_d5_waiver_recheck(registries: list[SpecRegistry]) -> None:
    for reg in registries:
        route = reg.outcome_route("T5", "exception")
        assert route is not None
        assert (route.destination, route.recheck_at, route.set_by) == (
            "T6",
            ("T6", "T8"),
            ("risk_owner",),
        )


def test_d6_package_binding(registries: list[SpecRegistry]) -> None:
    for reg in registries:
        entry = reg.entry("T4")
        assert entry is not None
        assert (
            entry.spec["terminal"]["evidence"]["ledger"]["bound_to"]
            == "T3.candidate_package.sha256"
        )


def test_d7_event_and_reentry(registries: list[SpecRegistry]) -> None:
    for reg in registries:
        drift = reg.event_route("T8", "T8.event.drift")
        assert drift is not None and drift.destination == "T9"
        change = reg.change_class_route("T9", "moderate")
        assert change is not None and change.reentry_terminal == "T2"


def test_d9_clarification_limits(registries: list[SpecRegistry]) -> None:
    for reg in registries:
        timeline = reg.timeline("T2", "medium")
        assert timeline is not None
        assert (timeline.max_clarification_rounds, timeline.clarification_sla) == (2, "3d")


def test_unknown_keys_are_empty(registries: list[SpecRegistry]) -> None:
    for reg in registries:
        assert reg.terminals_opened_by("no.such_event") == ()
        assert reg.outcome_route("T4", "rework", "gremlins") is None
        assert reg.outcome_route("T99", "pass") is None
        assert reg.event_route("T8", "T8.event.nothing") is None
        assert reg.timeline("T99", "low") is None
        assert reg.entry("T99") is None
        assert reg.catalogue("nope") is None


def test_disabled_status(registries: list[SpecRegistry]) -> None:
    for reg in registries:
        route = reg.outcome_route("T7", "exception")
        assert route is not None and route.kind == "disabled"


def test_catalogue_lookup(registries: list[SpecRegistry]) -> None:
    for reg in registries:
        guardrails = reg.catalogue("guardrails")
        assert guardrails is not None and guardrails.version == "1.0.0"
        assert guardrails.content["catalogue"] == "guardrails"


def test_both_registries_agree(registries: list[SpecRegistry]) -> None:
    sql, memory = registries
    for terminal in (f"T{n}" for n in range(10)):
        for status in ("pass", "rework", "exception", "escalate", "terminate"):
            assert sql.outcome_route(terminal, status) == memory.outcome_route(terminal, status)
        for tier in ("low", "medium", "high"):
            assert sql.timeline(terminal, tier) == memory.timeline(terminal, tier)
