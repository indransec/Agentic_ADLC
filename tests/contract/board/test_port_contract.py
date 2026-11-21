"""The ``BoardAdapter`` contract every adapter passes (T010, FR-025, contracts/board-port.md)."""

from __future__ import annotations

import pytest

from adlc.engagement.model import ItemWrite
from adlc.engagement.port import BoardAuthFailed, ItemNotFound, RevisionConflict
from tests.contract.board.conftest import (
    AREA,
    DECISION,
    EPIC,
    EPIC_STATES,
    PERSON,
    SERVICE,
    STATE,
    TASK,
    TITLE,
    Boards,
)


def test_check_describes_the_process(board: Boards) -> None:
    info = board.service.check()
    assert EPIC in info.types and TASK in info.types
    assert set(EPIC_STATES) <= set(info.types[EPIC].states)
    assert {TITLE, STATE, DECISION} <= info.types[TASK].fields
    assert AREA in info.areas


def test_create_with_parent_and_get(board: Boards) -> None:
    epic = board.service.create(EPIC, {TITLE: "Use case"})
    task = board.service.create(TASK, {TITLE: "Run"}, parent_id=epic.id)
    read = board.service.get(task.id)
    assert read.type == TASK
    assert read.fields[TITLE] == "Run"
    assert read.parent_id == epic.id
    assert read.changed_by == SERVICE
    assert board.service.get(epic.id).parent_id is None


def test_get_at_an_older_revision(board: Boards) -> None:
    item = board.service.create(TASK, {TITLE: "first"})
    board.service.update(item.id, ItemWrite(set={TITLE: "second"}, expected_rev=item.rev))
    assert board.service.get_at(item.id, item.rev).fields[TITLE] == "first"
    assert board.service.get(item.id).fields[TITLE] == "second"


def test_update_checks_the_revision(board: Boards) -> None:
    item = board.service.create(TASK, {TITLE: "t"})
    changed = board.person.update(item.id, ItemWrite(set={DECISION: "Pass"}))
    assert changed.rev == item.rev + 1 and changed.changed_by == PERSON
    with pytest.raises(RevisionConflict):
        board.service.update(item.id, ItemWrite(set={TITLE: "stale"}, expected_rev=item.rev))
    current = board.service.get(item.id)
    assert current.fields[TITLE] == "t" and current.rev == changed.rev


def test_set_and_clear_in_one_write(board: Boards) -> None:
    item = board.service.create(TASK, {TITLE: "t", DECISION: "Pass"})
    after = board.service.update(
        item.id, ItemWrite(set={TITLE: "u"}, clear=(DECISION,), expected_rev=item.rev)
    )
    assert after.fields[TITLE] == "u"
    assert after.fields.get(DECISION) in (None, "")


def test_comment(board: Boards) -> None:
    item = board.service.create(TASK, {TITLE: "t"})
    board.service.comment(item.id, "ADLC: accepted")
    with pytest.raises(ItemNotFound):
        board.service.comment(10**8, "x")


def test_changes_since_a_watermark_exactly_once(board: Boards) -> None:
    first = board.service.changed_since(None)
    item = board.service.create(TASK, {TITLE: "polled"})
    seen = {u.update_id for u in board.service.updates(item.id)}
    assert seen, "a created item has its creation update"
    page = board.service.changed_since(first.as_of)
    assert item.id in page.item_ids
    board.person.update(item.id, ItemWrite(set={DECISION: "Rework"}))
    later = board.service.changed_since(page.as_of)
    assert item.id in later.item_ids
    new = board.service.updates(item.id, after_update_id=max(seen))
    assert [u.changed_by for u in new] == [PERSON]
    assert new[0].fields[DECISION].new == "Rework"
    assert new[0].update_id > max(seen) and new[0].is_revision
    assert board.service.updates(item.id, after_update_id=new[0].update_id) == []


def test_parent_side_update_keeps_the_revision(board: Boards) -> None:
    epic = board.service.create(EPIC, {TITLE: "Use case"})
    before = board.service.get(epic.id).rev
    child = board.service.create(TASK, {TITLE: "Run"}, parent_id=epic.id)
    assert board.service.get(epic.id).rev == before
    link_updates = [u for u in board.service.updates(epic.id) if not u.is_revision]
    assert len(link_updates) == 1, "the parent records its new child without a revision"
    assert link_updates[0].rev == before
    assert board.service.get(child.id).parent_id == epic.id


def test_find_identity(board: Boards) -> None:
    found = board.service.find_identity(PERSON)
    assert found is not None and found.unique_name == PERSON
    assert board.service.find_identity("nobody@example.test") is None


def test_unknown_item(board: Boards) -> None:
    for call in (
        lambda: board.service.get(10**8),
        lambda: board.service.update(10**8, ItemWrite(set={TITLE: "x"})),
        lambda: board.service.updates(10**8),
    ):
        with pytest.raises(ItemNotFound):
            call()


def test_a_refused_token(board: Boards) -> None:
    with pytest.raises(BoardAuthFailed):
        board.with_bad_token().check()
