"""014 T014 (FR-006, SC-005): no agent can set an outcome or approve anything people decide; no
tool lets an agent decide; an unauthorised package is not deployable (the deploy argument is bound
by the platform: tests/integration/agents/test_acting_scopes.py)."""

import pytest

from adlc.inbox.changes import ChangeService
from adlc.inbox.proposed_events import ProposedEventService
from adlc.orchestration.service import Actor, NotAuthorised
from adlc.spec_toolkit.registry import SqlSpecRegistry
from adlc.tools.catalogue import CATALOGUE
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness

AGENT = Actor(
    "agent:UC-0001/T1/run-1", frozenset({"product_owner", "release_manager", "risk_owner"}), "agent"
)
OUTCOME_WORDS = (
    "decide",
    "approve",
    "sign",
    "pass",
    "waiver",
    "authoris",
    "release_kill",
    "accept",
)


def test_an_agent_cannot_decide_answer_or_approve(h: Harness) -> None:
    usecase, run = walk_to(h, "T1")
    h.drain()
    with pytest.raises(NotAuthorised):
        h.service.decide(AGENT, run, "pass")
    with pytest.raises(NotAuthorised):
        h.service.decide(AGENT, run, "exception", fields={"expiry": "2099-01-01"})
    with pytest.raises(NotAuthorised):
        h.service.decide_waiver(AGENT, "WVR-0001", True)
    with pytest.raises(NotAuthorised):
        h.service.complete_escalation(AGENT, run, {})
    with pytest.raises(NotAuthorised):
        h.service.answer_clarification(AGENT, f"{run}/clar-1", ["x"])
    with pytest.raises(NotAuthorised):
        ChangeService(h.app, SqlSpecRegistry(h.app), h.service, h.clock).decide(
            AGENT, "CHG-1", True, ""
        )
    with pytest.raises(NotAuthorised):
        ProposedEventService(h.orch.runs, h.service).decide(AGENT, run, "EV-1", True, "")
    assert h.run(run).state == "awaiting_sign_off"  # nothing changed
    assert usecase


def test_no_tool_sets_an_outcome() -> None:
    names = [t.name for t in CATALOGUE.tools.values()]
    assert not [n for n in names if any(w in n for w in OUTCOME_WORDS)], names
