"""T014: the decision form is built from the pinned spec, for every terminal (research R-04)."""

from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from adlc.inbox.forms import build_form
from adlc.orchestration import spec_view
from adlc.orchestration.service import Actor
from adlc.orchestration.states import RunState, TransitionContext
from adlc.orchestration.store import RunRow
from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.registry import InMemorySpecRegistry

SPECS = Path(__file__).resolve().parents[3] / "adlc-specs"
TERMINALS = [f"T{n}" for n in range(9)]


@cache
def registry() -> InMemorySpecRegistry:
    return InMemorySpecRegistry.from_bundle(load_bundle(SPECS))


def kinds() -> dict[str, str]:
    catalogue = registry().catalogue("route_destinations")
    items = (catalogue.content if catalogue else {}).get("route_destinations", [])
    return {str(i["id"]): str(i["kind"]) for i in items}


def run_row(terminal: str, **over: Any) -> RunRow:
    entry = registry().entry(terminal)
    assert entry is not None
    values: dict[str, Any] = {
        "run_id": f"UC-0001/{terminal}/run-1",
        "usecase_id": "UC-0001",
        "terminal_id": terminal,
        "run_number": 1,
        "spec_version": entry.version,
        "state": RunState.AWAITING_SIGN_OFF,
        "return_state": None,
        "mode": "normal",
        "trigger_event_id": None,
        "trigger_event_type": "x",
        "trigger_context": {},
        "rework_count": 0,
        "auto_retries": 0,
        "clarification_rounds": 0,
        "artifacts": {},
        "control_results": [],
        "recommendation": None,
        "received_events": [],
        "pending_waiver_id": None,
        "escalation_trigger": None,
        "escalation_destination": None,
        "final_status": None,
        "version": 3,
        "lease_until": None,
        "opened_at": datetime.now(UTC),
        "due_at": None,
        "closed_at": None,
    }
    values.update(over)
    return RunRow(**values)


def ctx_for(spec: Any) -> TransitionContext:
    rule = spec_view.sign_off_rule(spec, "medium", "normal")
    return TransitionContext(min_approvers=rule.min_approvers, rule_roles=rule.roles)


def form(terminal: str, actor: Actor, **over: Any) -> dict[str, Any]:
    entry = registry().entry(terminal)
    assert entry is not None
    ctx = over.pop("ctx", None) or ctx_for(entry.spec)
    return build_form(
        spec=entry.spec,
        run=run_row(terminal, **over),
        ctx=ctx,
        actor=actor,
        registry=registry(),
        destination_kind=kinds().get,
        catalogue_root_causes=(),
        pinned_terminals=TERMINALS,
    )


@pytest.mark.parametrize("terminal", TERMINALS)
def test_outcomes_and_requirements_come_from_the_spec(terminal: str) -> None:
    entry = registry().entry(terminal)
    assert entry is not None
    spec = entry.spec
    role = sorted(ctx_for(spec).rule_roles)[0]
    built = form(terminal, Actor(f"{role}-person", frozenset({role})))
    rights = spec_view.status_rights(spec, "human")
    assert set(built["outcomes"]) <= set(rights)
    for status in built["outcomes"]:
        assert built["requires"][status] == list(spec_view.outcome_requires(spec, status))
    assert built["root_causes"] == list(spec_view.rework_causes(spec))
    assert built["can_decide"] and built["sign_off_role"] == role


def test_t1_form() -> None:
    owner = Actor("po", frozenset({"product_owner"}))
    built = form("T1", owner)
    assert built["outcomes"] == ["pass", "rework", "exception", "terminate"]
    assert built["requires"]["exception"] == ["waiver_owner", "expiry", "compensating_control"]
    assert built["requires"]["rework"] == ["owner_comment"]
    assert built["root_causes"] == ["requirement", "qualification"]
    assert built["can_edit"] and built["reason_required_unless"] is None


def test_typed_values_and_resolver_causes() -> None:
    """Values a pass emits that no artifact supplies are typed in; resolver routes need a target."""
    for terminal in TERMINALS:
        entry = registry().entry(terminal)
        assert entry is not None
        role = sorted(ctx_for(entry.spec).rule_roles)[0]
        built = form(terminal, Actor("p", frozenset({role})))
        assert set(built["target_terminal_for"]) <= set(built["root_causes"])
        assert isinstance(built["typed_fields"], list)
    t0 = form("T0", Actor("p", frozenset({"business_owner"})))
    assert "risk_tier" in t0["typed_fields"]


def test_who_may_act() -> None:
    stranger = Actor("x", frozenset({"sre"}))
    built = form("T1", stranger)
    assert not built["can_decide"] and not built["can_edit"] and built["sign_off_role"] is None
    owner = Actor("po", frozenset({"product_owner"}))
    assert not form("T1", owner, controls_pending=True)["can_decide"]
    assert not form("T1", owner, state=RunState.BUILDING)["can_decide"]
    already = TransitionContext(
        min_approvers=2,
        rule_roles=frozenset({"product_owner", "business_owner"}),
        approvals=(("po", "product_owner"),),
    )
    assert form("T1", owner, ctx=already)["sign_off_role"] is None


def test_reason_needed_when_differing_from_the_reviewer() -> None:
    owner = Actor("po", frozenset({"product_owner"}))
    built = form("T1", owner, recommendation={"status": "rework", "root_cause": "requirement"})
    assert built["reason_required_unless"] == "rework"
