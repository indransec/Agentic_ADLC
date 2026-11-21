"""SC-005: a 10-minute board outage with changes on both sides; afterwards everything is
delivered once (T056)."""

from __future__ import annotations

from datetime import timedelta

from adlc.engagement.model import ItemWrite
from tests.support.board import Rig, needed_roles
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness


def test_an_outage_loses_and_repeats_nothing(h: Harness) -> None:
    rig = Rig(h)
    usecase, run_id = walk_to(h, "T1")
    other, other_run = walk_to(h, "T1")
    rig.cycle()
    role = needed_roles(h, run_id)[0]
    rig.as_role(role).update(  # saved on the board just before it went down
        rig.item("run", run_id),
        ItemWrite(set={rig.mapping.decision_field: rig.mapping.value_for("pass")}),
    )
    rig.board.unreachable = True
    h.pass_run(other_run)  # the platform moves on while the board is down
    for _ in range(20):  # ten minutes of polling and projecting, every 30 seconds
        h.clock.advance(timedelta(seconds=30))
        rig.projector.run_once()
        assert rig.sync.poll().outcome == "board_unreachable"
    assert rig.projector.delivery_summary()["dead_lettered"] == []  # still retrying
    rig.board.unreachable = False
    h.clock.advance(timedelta(minutes=15))
    rig.cycle()
    assert h.sql("SELECT count(*) FROM sign_off WHERE run_id = :r", r=run_id)[0][0] == 1
    epic = rig.board.get(rig.item("usecase", other))
    assert epic.fields[rig.mapping.field("usecase", "state")] == rig.mapping.column("T2")
    assert rig.projector.delivery_summary()["pending"] == 0
    assert usecase
