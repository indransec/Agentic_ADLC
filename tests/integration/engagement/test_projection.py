"""US1: the board follows the platform (T022, T025; FR-005..FR-009)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from adlc.engagement.fake import FakeBoard
from adlc.engagement.mapping import TrackerMapping
from adlc.engagement.projector import Projector
from adlc.orchestration.outbox import RETRY_DELAYS
from tests.support.board import EVIDENCE, fake_board, inbox_for, mapping
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person


@pytest.fixture
def tracker() -> TrackerMapping:
    return mapping()


@pytest.fixture
def board(tracker: TrackerMapping) -> FakeBoard:
    return fake_board(tracker)


@pytest.fixture
def projector(h: Harness, board: FakeBoard, tracker: TrackerMapping) -> Projector:
    return Projector(h.app, inbox_for(h), board, tracker, EVIDENCE, h.clock)


def _items(board: FakeBoard, tracker: TrackerMapping, kind: str) -> list:  # type: ignore[type-arg]
    item_type = tracker.item(kind).type
    return [board.get(i) for i in board.item_ids() if board.get(i).type == item_type]


def test_the_board_shows_a_use_case_at_sign_off(
    h: Harness, board: FakeBoard, tracker: TrackerMapping, projector: Projector
) -> None:
    usecase, run_id = walk_to(h, "T1")
    projector.run_once()
    [epic] = _items(board, tracker, "usecase")
    assert epic.fields[tracker.field("usecase", "usecase_id")] == usecase
    assert epic.fields[tracker.field("usecase", "state")] == tracker.column("T1")
    assert epic.fields[tracker.field("usecase", "sub_stage")] == tracker.sub_stage(
        "awaiting_sign_off"
    )
    runs = {r.fields[tracker.field("run", "run_id")]: r for r in _items(board, tracker, "run")}
    assert run_id in runs and len(runs) == 2  # T0's closed run and T1's open one
    t1 = runs[run_id]
    assert t1.parent_id == epic.id
    assert t1.fields[tracker.field("run", "evidence")].startswith(EVIDENCE)
    assert tracker.value_for("pass") in t1.fields[tracker.field("run", "description")]
    assert all(r.changed_by == board.service_identity for r in runs.values())


def test_each_transition_follows(
    h: Harness, board: FakeBoard, tracker: TrackerMapping, projector: Projector
) -> None:
    usecase, run_id = walk_to(h, "T1")
    projector.run_once()
    h.pass_run(run_id)  # decided through the inbox path (FR-009)
    projector.run_once()
    [epic] = _items(board, tracker, "usecase")
    assert epic.fields[tracker.field("usecase", "state")] == tracker.column("T2")
    states = {r.fields[tracker.field("run", "run_id")]: r for r in _items(board, tracker, "run")}
    assert states[run_id].fields[tracker.field("run", "state")] == tracker.run_item_state("closed")
    assert usecase


def test_a_second_pass_with_nothing_new_writes_nothing(
    h: Harness, board: FakeBoard, projector: Projector
) -> None:
    usecase, _ = walk_to(h, "T1")
    projector.run_once()
    revisions = {i: board.get(i).rev for i in board.item_ids()}
    projector.run_once()
    projector.deliver(usecase)  # forced delivery: the hashes match, nothing is written
    assert {i: board.get(i).rev for i in board.item_ids()} == revisions


def test_a_use_case_appears_before_its_first_run(
    h: Harness, board: FakeBoard, tracker: TrackerMapping, projector: Projector
) -> None:
    h.service.submit_usecase(person("business_owner"), "Early", "x" * 250)  # not drained
    projector.run_once()
    [epic] = _items(board, tracker, "usecase")
    assert epic.fields[tracker.field("usecase", "title")] == "Early"
    assert epic.fields[tracker.field("usecase", "area")] == tracker.area


def test_an_outage_never_blocks_the_platform_and_retries(
    h: Harness, board: FakeBoard, tracker: TrackerMapping, projector: Projector
) -> None:
    board.unreachable = True
    usecase, run_id = walk_to(h, "T1")  # the platform works while the board is down
    for delay in RETRY_DELAYS:
        projector.run_once()
        h.clock.advance(delay)
    projector.run_once()  # fifth failure: dead letter
    health = projector.delivery_summary()
    assert health["dead_lettered"] == [usecase]
    board.unreachable = False
    h.clock.advance(timedelta(hours=1))
    projector.run_once()
    assert board.item_ids() == []  # dead: nothing until requeued
    assert projector.requeue(usecase, "coe.lead")
    projector.run_once()
    assert [
        e.fields[tracker.field("usecase", "usecase_id")] for e in _items(board, tracker, "usecase")
    ] == [usecase]
    assert run_id
