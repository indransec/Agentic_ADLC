"""Exactly once across overlaps and stops (T028; FR-012; research R-07)."""

from __future__ import annotations

import pytest

from adlc.engagement import store
from adlc.engagement.model import ItemWrite
from tests.support.board import Rig
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness


@pytest.fixture
def rig(h: Harness) -> Rig:
    return Rig(h)


def _pass_saved(rig: Rig, h: Harness) -> tuple[str, int, int]:
    _, run_id = walk_to(h, "T1")
    rig.cycle()
    run = h.run(run_id)
    with h.app.connect() as conn:
        role = sorted(h.orch.runs.context(conn, run).rule_roles)[0]
    item = rig.item("run", run_id)
    saved = rig.as_role(role).update(
        item, ItemWrite(set={rig.mapping.decision_field: rig.mapping.value_for("pass")})
    )
    update = rig.board.updates(item)[-1]
    assert update.rev == saved.rev
    return run_id, item, update.update_id


def test_a_claim_is_taken_once(rig: Rig, h: Harness) -> None:
    run_id, item, update = _pass_saved(rig, h)
    change = store.Claim(item, update, 1, "x", None, "decide", run_id)
    with h.app.begin() as conn:
        assert store.claim(conn, change, h.clock.now())
    rig.sync.poll()  # the update is already claimed: no command
    assert h.sql("SELECT count(*) FROM sign_off WHERE run_id = :r", r=run_id)[0][0] == 0


def test_a_stop_after_the_command_is_recovered_as_accepted(rig: Rig, h: Harness) -> None:
    run_id, item, update = _pass_saved(rig, h)
    rig.sync.poll()
    signed = h.sql("SELECT count(*) FROM sign_off WHERE run_id = :r", r=run_id)[0][0]
    assert signed == 1
    # pretend the process stopped between the command and its outcome
    with h.app.begin() as conn:
        conn.exec_driver_sql("DROP TRIGGER inbound_outcome_no_delete")
        conn.exec_driver_sql(
            f"DELETE FROM inbound_outcome WHERE work_item_id = {item} AND update_id = {update}"
        )
    assert rig.sync.recover() == 1
    outcome = h.sql(
        "SELECT outcome, command FROM inbound_outcome WHERE work_item_id = :i AND update_id = :u",
        i=item,
        u=update,
    )
    assert outcome[0][0] == "accepted"
    assert h.sql("SELECT count(*) FROM sign_off WHERE run_id = :r", r=run_id)[0][0] == signed


def test_a_stop_before_the_command_is_applied_again(rig: Rig, h: Harness) -> None:
    run_id, item, update = _pass_saved(rig, h)
    with h.app.begin() as conn:  # claimed, then the process stopped before the command
        store.claim(conn, store.Claim(item, update, 1, "x", None, "decide", run_id), h.clock.now())
    assert rig.sync.recover() == 1
    assert h.sql("SELECT count(*) FROM sign_off WHERE run_id = :r", r=run_id)[0][0] == 1
    assert rig.sync.recover() == 0
