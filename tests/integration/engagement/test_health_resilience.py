"""US9: sync health, restarts, first start and failures (T048; FR-010, FR-010a, FR-022)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from adlc.engagement import store
from adlc.engagement.health import health
from adlc.engagement.inbound import InboundSync
from adlc.engagement.model import BoardUpdate, ItemWrite
from tests.support.board import Rig, needed_roles
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness


@pytest.fixture
def rig(h: Harness) -> Rig:
    return Rig(h)


def _approvals(h: Harness, run_id: str) -> list[tuple[str, str]]:
    with h.app.connect() as conn:
        return list(h.orch.runs.context(conn, h.run(run_id)).approvals)


def _watermark(h: Harness) -> str | None:
    with h.app.connect() as conn:
        return store.sync_state(conn).watermark


def _new_sync(rig: Rig, start_from: str | None = None) -> InboundSync:
    return InboundSync(
        rig.h.app,
        rig.h.service,
        rig.board,
        rig.mapping,
        rig.identities,
        rig.projector,
        rig.h.clock,
        start_from,
    )


def test_health_fields(rig: Rig, h: Harness) -> None:
    walk_to(h, "T1")
    rig.cycle()
    body = health(h.app, enabled=True, now=h.clock.now())
    assert set(body) == {
        "enabled",
        "mapping_ok",
        "last_poll_at",
        "last_poll_outcome",
        "watermark",
        "watermark_age_s",
        "outbound_pending",
        "outbound_oldest_age_s",
        "dead_lettered",
        "refused_by_reason",
        "reverted_count",
        "last_reconciliation",
    }
    assert body["last_poll_outcome"] == "ok" and body["outbound_pending"] == 0
    assert body["watermark"] is not None


def test_a_restart_resumes_from_the_stored_watermark(rig: Rig, h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    rig.cycle()
    run = h.run(run_id)
    with h.app.connect() as conn:
        role = sorted(h.orch.runs.context(conn, run).rule_roles)[0]
    rig.as_role(role).update(
        rig.item("run", run_id),
        ItemWrite(set={rig.mapping.decision_field: rig.mapping.value_for("pass")}),
    )
    restarted = _new_sync(rig)  # a new process: no memory but the tables
    restarted.poll()
    restarted.poll()
    assert h.sql("SELECT count(*) FROM sign_off WHERE run_id = :r", r=run_id)[0][0] == 1


def test_first_start_against_a_board_with_history_replays_nothing(h: Harness) -> None:
    rig = Rig(h)
    with h.app.begin() as conn:  # forget the empty-board start of Rig()
        conn.exec_driver_sql("UPDATE board_sync_state SET watermark = NULL")
    f = rig.mapping.item("usecase").fields
    rig.as_role("business_owner").create(
        rig.mapping.item("usecase").type,
        {f["title"]: "Old epic", f["description"]: "from before", f["area"]: rig.mapping.area},
    )
    _new_sync(rig).poll()  # first start: baseline
    assert h.sql("SELECT count(*) FROM usecase")[0][0] == 0
    kinds = {r[0] for r in h.sql("SELECT kind FROM inbound_change")}
    assert kinds == {"baseline"}
    assert _watermark(h) is not None


def test_start_from_overrides_the_baseline(h: Harness) -> None:
    rig = Rig(h)
    with h.app.begin() as conn:
        conn.exec_driver_sql("UPDATE board_sync_state SET watermark = NULL")
    f = rig.mapping.item("usecase").fields
    rig.as_role("business_owner").create(
        rig.mapping.item("usecase").type,
        {f["title"]: "Wanted", f["description"]: "register me", f["area"]: rig.mapping.area},
    )
    _new_sync(rig, start_from="2000-01-01T00:00:00Z").poll()
    assert [r[0] for r in h.sql("SELECT name FROM usecase")] == ["Wanted"]


def test_a_failing_item_leaves_the_watermark(rig: Rig, h: Harness) -> None:
    walk_to(h, "T1")
    rig.cycle()
    before = _watermark(h)
    rig.as_role("product_owner").update(1, ItemWrite(set={"System.Tags": "x"}))
    with patch.object(InboundSync, "_process", side_effect=RuntimeError("boom")):
        rig.sync.poll()
    assert _watermark(h) == before
    rig.sync.poll()  # recovered: read and moved on
    assert _watermark(h) != before


def test_a_failing_item_does_not_hold_back_the_others(rig: Rig, h: Harness) -> None:
    """Found in 018's live walk: one item that cannot be handled must not stop the poll for every
    other item; the watermark still waits for it (016 research, inbound step 4)."""
    usecase, run_id = walk_to(h, "T1")
    rig.cycle()
    before = _watermark(h)
    epic, run = rig.item("usecase", usecase), rig.item("run", run_id)
    rig.as_role("product_owner").update(epic, ItemWrite(set={"System.Tags": "first"}))
    role = needed_roles(h, run_id)[0]
    rig.as_role(role).update(
        run, ItemWrite(set={rig.mapping.decision_field: rig.mapping.value_for("pass")})
    )
    handle = InboundSync._process

    def failing_for_the_epic(self: InboundSync, update: BoardUpdate, **kwargs: bool) -> None:
        if update.item_id == epic:
            raise RuntimeError("boom")
        handle(self, update, **kwargs)

    with patch.object(InboundSync, "_process", failing_for_the_epic):
        rig.sync.poll()
    assert _watermark(h) == before
    assert ("accepted", None) in rig.outcomes()  # the run item's decision was read
    assert role in {r for _, r in _approvals(h, run_id)}


def test_a_refused_token_is_recorded_and_the_platform_carries_on(rig: Rig, h: Harness) -> None:
    rig.sync.board = rig.board.with_token_refused()
    rig.projector.board = rig.sync.board
    assert rig.sync.poll().outcome == "auth_failed"
    usecase, _ = walk_to(h, "T1")  # the platform works on
    with h.app.connect() as conn:
        assert store.sync_state(conn).last_poll_outcome == "auth_failed"
    assert usecase
