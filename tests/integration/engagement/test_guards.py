"""US6: the board cannot get ahead of the platform (T041; FR-016, FR-017; D-12)."""

from __future__ import annotations

import pytest

from adlc.engagement.model import ItemWrite
from tests.support.board import FREE_FIELD, Rig
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness


@pytest.fixture
def rig(h: Harness) -> Rig:
    return Rig(h)


def test_a_dragged_epic_goes_back(rig: Rig, h: Harness) -> None:
    usecase, _ = walk_to(h, "T1")
    rig.cycle()
    state = rig.mapping.field("usecase", "state")
    item = rig.item("usecase", usecase)
    rig.as_role("product_owner").update(item, ItemWrite(set={state: rig.mapping.column("T5")}))
    rig.cycle()
    assert rig.board.get(item).fields[state] == rig.mapping.column("T1")
    assert any("set by the platform" in c for c in rig.comments("usecase", usecase))
    assert rig.outcomes()[-1] == ("refused", "platform_field")


def test_a_run_item_field_goes_back_and_the_request_still_counts(rig: Rig, h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    rig.cycle()
    item = rig.item("run", run_id)
    title = rig.mapping.field("run", "title")
    before = rig.board.get(item).fields[title]
    rig.as_role("product_owner").update(item, ItemWrite(set={title: "renamed", FREE_FIELD: "tag"}))
    rig.cycle()
    current = rig.board.get(item).fields
    assert current[title] == before
    assert current[FREE_FIELD] == "tag"  # a field the mapping does not read is left alone


def test_a_free_field_alone_is_ignored(rig: Rig, h: Harness) -> None:
    usecase, _ = walk_to(h, "T1")
    rig.cycle()
    rig.as_role("product_owner").update(
        rig.item("usecase", usecase), ItemWrite(set={FREE_FIELD: "x"})
    )
    rig.cycle()
    assert rig.outcomes()[-1] == ("ignored", None)


def test_the_platform_s_own_writes_are_never_requests(rig: Rig, h: Harness) -> None:
    walk_to(h, "T1")
    rig.cycle()
    kinds = {r[0] for r in h.sql("SELECT kind FROM inbound_change")}
    assert kinds <= {"own", "baseline"}


def test_a_refusal_never_overwrites_a_later_change(rig: Rig, h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    rig.cycle()
    item = rig.item("run", run_id)
    decision = rig.mapping.decision_field
    rig.as_role("sre").update(
        item, ItemWrite(set={decision: rig.mapping.value_for("pass")})
    )  # no right
    rig.as_role("sre").update(item, ItemWrite(set={decision: "Maybe"}))  # a later change, unread
    rig.sync.poll()
    first, second = rig.outcomes()[-2:]
    assert first == ("refused", "not_authorised") and second == ("refused", "unknown_value")
    assert rig.board.get(item).fields.get(decision) in (None, "")
