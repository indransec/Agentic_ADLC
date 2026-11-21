"""US7: reconciling the board with the platform (T043; FR-019, FR-020; D-13)."""

from __future__ import annotations

import pytest

from adlc.engagement.model import ItemWrite
from adlc.engagement.reconcile import Reconciler
from adlc.orchestration.service import NotAuthorised
from tests.support.board import Rig
from tests.support.lifecycle import walk_to
from tests.support.orchestration import DEADLETTER_ROLE, Harness, person

PLATFORM_TABLES = (
    "usecase",
    "terminal_run",
    "run_transition",
    "run_activity",
    "sign_off",
    "outbox_event",
)


@pytest.fixture
def rig(h: Harness) -> Rig:
    return Rig(h)


@pytest.fixture
def reconciler(rig: Rig, h: Harness) -> Reconciler:
    return Reconciler(h.app, rig.projector, rig.board, rig.mapping, h.clock, DEADLETTER_ROLE)


def _platform(h: Harness) -> dict[str, int]:
    return {t: h.sql(f"SELECT count(*) FROM {t}")[0][0] for t in PLATFORM_TABLES}  # noqa: S608


def test_differences_are_corrected_and_reported(
    rig: Rig, h: Harness, reconciler: Reconciler
) -> None:
    usecase, run_id = walk_to(h, "T1")
    rig.cycle()
    epic, run = rig.item("usecase", usecase), rig.item("run", run_id)
    state, title = rig.mapping.field("usecase", "state"), rig.mapping.field("run", "title")
    # changed behind the sync's back (an administrator, a restored board)
    rig.board.update(epic, ItemWrite(set={state: rig.mapping.column("T4")}))
    rig.board.update(run, ItemWrite(set={title: "tampered"}))
    before = _platform(h)
    report = reconciler.reconcile(person(DEADLETTER_ROLE))
    assert _platform(h) == before  # never changes the platform
    found = {(d["object_id"], d["field"]) for d in report["differences"]}
    assert found == {(usecase, state), (run_id, title)}
    assert all(
        d["action"] == "corrected" and len(d["board_value_hash"]) == 16
        for d in report["differences"]
    )
    assert rig.board.get(epic).fields[state] == rig.mapping.column("T1")
    assert reconciler.reconcile(person(DEADLETTER_ROLE))["differences"] == []


def test_missing_items_are_created_and_linked(rig: Rig, h: Harness, reconciler: Reconciler) -> None:
    usecase, run_id = walk_to(h, "T1")  # never projected (from before the feature)
    report = reconciler.reconcile(person(DEADLETTER_ROLE))
    assert report["created_items"] >= 3  # the Epic and both runs
    assert rig.board.get(rig.item("run", run_id)).parent_id == rig.item("usecase", usecase)


def test_only_the_coe_role(reconciler: Reconciler) -> None:
    with pytest.raises(NotAuthorised):
        reconciler.reconcile(person("product_owner"))


def test_an_unread_decision_is_left_for_inbound_sync(
    rig: Rig, h: Harness, reconciler: Reconciler
) -> None:
    _, run_id = walk_to(h, "T1")
    rig.cycle()
    item = rig.item("run", run_id)
    rig.as_role("product_owner").update(
        item, ItemWrite(set={rig.mapping.decision_field: rig.mapping.value_for("pass")})
    )
    reconciler.reconcile(person(DEADLETTER_ROLE))
    assert rig.board.get(item).fields[rig.mapping.decision_field] == rig.mapping.value_for("pass")


def test_reports_are_kept(h: Harness, reconciler: Reconciler) -> None:
    first = reconciler.reconcile(person(DEADLETTER_ROLE))
    assert reconciler.report(first["id"])["id"] == first["id"]  # type: ignore[index]
    assert reconciler.report(None)["id"] == first["id"]  # type: ignore[index]
