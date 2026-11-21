"""US4: answering a clarification from the board (T037)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from adlc.engagement.model import ItemWrite
from adlc.orchestration.interfaces import Clarification
from adlc.orchestration.stubs import StubAgent
from tests.support.board import Rig
from tests.support.db import PlatformDatabase
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, harness, person

ASK = Clarification(("Which channels are in scope?", "Which regions?"))
ADDRESSED = "engineering_lead"  # T2's first R role (FR-023a)


@pytest.fixture
def asked(orch_template: PlatformDatabase) -> Iterator[tuple[Harness, Rig, str]]:
    with harness(orch_template, agent=StubAgent({"T2": {1: ASK}})) as h:
        rig = Rig(h)
        _, run_id = walk_to(h, "T2")
        rig.cycle()
        yield h, rig, f"{run_id}/clar-1"


def _answer(rig: Rig, role: str, clarification_id: str, text: str) -> None:
    field = rig.mapping.field("clarification", "answer")
    rig.as_role(role).update(
        rig.item("clarification", clarification_id), ItemWrite(set={field: text})
    )


def _task(rig: Rig, clarification_id: str) -> dict[str, object]:
    return dict(rig.board.get(rig.item("clarification", clarification_id)).fields)


def test_answered_by_the_addressed_role(asked: tuple[Harness, Rig, str]) -> None:
    h, rig, clar = asked
    assert (
        _task(rig, clar)[rig.mapping.field("clarification", "state")]
        == rig.mapping.clarification_open
    )
    _answer(rig, ADDRESSED, clar, "1. Web and email\n2. EU only")
    rig.cycle()
    answers = h.sql("SELECT answered_by, answers FROM clarification_answer")[0]
    assert answers[0] == person(ADDRESSED).account_name
    assert list(answers[1]) == ["Web and email", "EU only"]
    assert h.run(clar.rsplit("/", 1)[0]).state != "awaiting_clarification"
    assert (
        _task(rig, clar)[rig.mapping.field("clarification", "state")]
        == rig.mapping.clarification_answered
    )


def test_another_role_is_refused_and_cleared(asked: tuple[Harness, Rig, str]) -> None:
    h, rig, clar = asked
    _answer(rig, "product_owner", clar, "1. a\n2. b")
    rig.cycle()
    assert rig.outcomes()[-1] == ("refused", "not_authorised")
    assert _task(rig, clar).get(rig.mapping.field("clarification", "answer")) in (None, "")
    assert h.sql("SELECT count(*) FROM clarification_answer")[0][0] == 0


def test_a_count_mismatch_is_refused(asked: tuple[Harness, Rig, str]) -> None:
    _, rig, clar = asked
    _answer(rig, ADDRESSED, clar, "Just one answer")
    rig.cycle()
    assert rig.outcomes()[-1] == ("refused", "invalid_input")
    assert any("2 answers" in c for c in rig.comments("clarification", clar))


def test_already_answered_in_the_inbox(asked: tuple[Harness, Rig, str]) -> None:
    h, rig, clar = asked
    _answer(rig, ADDRESSED, clar, "1. a\n2. b")
    h.service.answer_clarification(person(ADDRESSED), clar, ["x", "y"])
    rig.cycle()
    assert rig.outcomes()[-1] == ("refused", "already_answered")
