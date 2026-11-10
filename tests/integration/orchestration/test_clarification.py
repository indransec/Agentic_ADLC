"""T052: clarifications pause and resume the same run (FR-023 to FR-025; US4)."""

from datetime import timedelta

import pytest

from adlc.orchestration.interfaces import Clarification
from adlc.orchestration.service import AlreadyAnswered, NotAuthorised
from adlc.orchestration.stubs import StubAgent, StubReviewer
from tests.support.lifecycle import walk_to
from tests.support.orchestration import harness, person
from tests.support.pg import PlatformDatabase

ASK = Clarification(("Which channels are in scope?",), looked_in=("intake", "T1.user_experience"))


def test_agent_clarification_round_trip(orch_template: PlatformDatabase) -> None:
    with harness(orch_template, agent=StubAgent({"T2": {1: ASK}})) as h:
        usecase, run_id = walk_to(h, "T2")
        run = h.run(run_id)
        assert (run.state, run.return_state, run.clarification_rounds) == (
            "awaiting_clarification",
            "building",
            1,
        )
        row = h.sql(
            "SELECT clarification_id, addressed_role, questions, looked_in FROM run.clarification_round"
        )[0]
        assert row[0] == f"{run_id}/clar-1"
        assert row[1] == "engineering_lead"  # T2's first R role (FR-023a)
        with pytest.raises(NotAuthorised):
            h.service.answer_clarification(person("product_owner"), row[0], ["web"])
        h.service.answer_clarification(person("engineering_lead"), row[0], ["web", "email"])
        with pytest.raises(AlreadyAnswered):
            h.service.answer_clarification(person("engineering_lead", "x"), row[0], ["phone"])
        h.drain()
        resumed = h.run(run_id)
        assert resumed.run_id == run_id and resumed.state == "awaiting_sign_off"
        assert resumed.rework_count == 0
        second = [c for c in h.agent.contexts if c.run_id == run_id][-1]
        assert second.clarifications[0]["answers"] == ["web", "email"]


def test_named_role_is_used(orch_template: PlatformDatabase) -> None:
    ask = Clarification(("Data class?",), addressed_role="data_owner")
    with harness(orch_template, agent=StubAgent({"T2": {1: ask}})) as h:
        walk_to(h, "T2")
        assert h.sql("SELECT addressed_role FROM run.clarification_round")[0][0] == "data_owner"


def test_round_limit_escalates(orch_template: PlatformDatabase) -> None:
    with harness(orch_template, agent=StubAgent({"T2": {1: ASK, 2: ASK, 3: ASK}})) as h:
        usecase, run_id = walk_to(h, "T2")
        for n in (1, 2):
            h.service.answer_clarification(person("engineering_lead"), f"{run_id}/clar-{n}", ["a"])
            h.drain()
        run = h.run(run_id)
        assert (run.state, run.escalation_trigger) == ("escalated", "clarification_limit")


def test_sla_escalates(orch_template: PlatformDatabase) -> None:
    with harness(orch_template, agent=StubAgent({"T2": {1: ASK}})) as h:
        usecase, run_id = walk_to(h, "T2")
        h.clock.advance(timedelta(days=4))  # T2 clarification_sla
        h.drain()
        assert h.run(run_id).escalation_trigger == "clarification_sla"


def test_reviewer_clarification_returns_to_review(orch_template: PlatformDatabase) -> None:
    with harness(orch_template, reviewer=StubReviewer({"T2": {1: ASK}})) as h:
        usecase, run_id = walk_to(h, "T2")
        assert h.run(run_id).return_state == "reviewing"
        h.service.answer_clarification(person("engineering_lead"), f"{run_id}/clar-1", ["web"])
        h.drain()
        assert h.run(run_id).state == "awaiting_sign_off"
        assert h.agent.calls["T2"] == 1  # not rebuilt
        assert h.reviewer.contexts[-1].clarifications[0]["answers"] == ["web"]
