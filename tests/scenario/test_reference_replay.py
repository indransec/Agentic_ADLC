"""T028 (US5, SC-001): the reference use cases replay through T0-T2 from recordings, with every
mandatory artifact present and every blocking control passing."""

import json
from dataclasses import replace

import pytest

from adlc.agents.replay import Reference, Replayer, Report, load_references, read_recording
from tests.support.grounded import grounded
from tests.support.orchestration import person
from tests.support.pg import REPO_ROOT, PlatformDatabase

REFERENCES = load_references(REPO_ROOT / "data" / "reference_usecases")
RECORDINGS = REPO_ROOT / "tests" / "fixtures" / "replays"


@pytest.mark.parametrize("ref", REFERENCES, ids=lambda r: r.id)
def test_reference_replays_to_t2(orch_template: PlatformDatabase, ref: Reference) -> None:
    with grounded(orch_template, read_recording(RECORDINGS / ref.id)) as g:
        result = Replayer(g.h.service, g.h.orch.runs, g.h.drain, lambda role: [person(role)]).run(
            ref
        )
    assert result.outcome == "completed", result.outcome
    assert [t.terminal_id for t in result.terminals] == ["T0", "T1", "T2"]
    assert result.ok and Report("recording", None, [result]).ok
    assert all(t.prompt_hash and t.playbook_hashes for t in result.terminals)
    assert result.terminals[0].citations >= 1 and result.terminals[2].citations >= 1


def test_unanswered_clarification_stops_the_use_case(orch_template: PlatformDatabase) -> None:
    ref = replace(REFERENCES[0], answers={})  # nothing prepared for any role
    ask = {
        "clarification": {
            "questions": ["Who signs off payouts?"],
            "addressed_role": "business_owner",
            "looked_in": ["sharepoint:/policies"],
        }
    }
    with grounded(orch_template, {"t0-intake-agent": [json.dumps(ask)]}) as g:
        result = Replayer(g.h.service, g.h.orch.runs, g.h.drain, lambda role: [person(role)]).run(
            ref
        )
    assert result.outcome == "unanswered clarification"
    assert not Report("recording", None, [result]).ok


def test_an_account_with_several_roles_does_not_block_two_approvers(
    orch_template: PlatformDatabase,
) -> None:
    """A rule needing two people still completes when one account holds both roles: the replay
    picks another holder of the second role (seen in a live account file)."""
    from adlc.orchestration.service import Actor

    # a directory name (the T0 prerequisite) that also holds a second role
    shared = Actor("business_owner-person", frozenset({"business_owner", "product_owner"}))

    def people(role: str) -> list[Actor]:
        return [shared, person(role)] if role in shared.roles else [person(role)]

    ref = REFERENCES[0]
    with grounded(orch_template, read_recording(RECORDINGS / ref.id)) as g:
        result = Replayer(g.h.service, g.h.orch.runs, g.h.drain, people).run(ref)
    assert result.outcome == "completed" and result.ok
