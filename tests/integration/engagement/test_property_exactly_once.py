"""SC-003: 500 board changes by several people across 20 use cases, with overlapping polls and a
restart, are each processed exactly once, in update order per item (T054)."""

from __future__ import annotations

import json
import random

from adlc.engagement.inbound import InboundSync
from adlc.engagement.model import ItemWrite
from tests.support.board import FREE_FIELD, Rig, needed_roles
from tests.support.orchestration import Harness

CHANGES, USECASES = 500, 20
PEOPLE = ("product_owner", "business_owner", "sre", "engineering_lead", "qa_eval_lead")


def test_every_change_once_in_order(h: Harness) -> None:
    rig = Rig(h)
    runs = []
    for n in range(USECASES):
        usecase = h.submit(f"Case {n}")
        h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
        runs.append(h.active(usecase, "T1").run_id)
    rig.cycle()
    chooser = random.Random(16)  # noqa: S311 - test data
    person_updates = 0
    for change in range(CHANGES):
        run_id = chooser.choice(runs)
        role = chooser.choice([*PEOPLE, *needed_roles(h, run_id)[:1]])
        kind = chooser.random()
        if kind < 0.5:
            write = {FREE_FIELD: f"tag {change}"}
        elif kind < 0.8:
            write = {rig.mapping.decision_field: rig.mapping.value_for("pass")}
        else:
            write = {rig.mapping.decision_field: f"Value {change}"}
        item = rig.item("run", run_id)
        before = rig.board.get(item).rev
        if rig.as_role(role).update(item, ItemWrite(set=write)).rev > before:
            person_updates += 1  # an identical value makes no board update
        if change % 25 == 24:
            rig.sync.poll()
            if change % 100 == 99:  # an overlapping poll: the watermark moved back
                with h.app.begin() as conn:
                    conn.exec_driver_sql(
                        "UPDATE board_sync_state SET watermark = '2000-01-01T00:00:00Z'"
                    )
            if change == CHANGES // 2:  # a restart: a new sync with only the tables
                rig.sync = InboundSync(
                    h.app, h.service, rig.board, rig.mapping, rig.identities, rig.projector, h.clock
                )
    for _ in range(3):
        rig.sync.poll()
    rows = h.sql(
        "SELECT c.work_item_id, c.update_id, c.kind, o.outcome, o.command, c.account_name "
        "FROM inbound_change c JOIN inbound_outcome o USING (work_item_id, update_id) "
        "WHERE c.changer <> :s AND c.kind NOT IN ('own', 'baseline')",
        s=rig.identities.service_identity,
    )
    assert len(rows) == person_updates  # every person's change read once, with one outcome
    assert len({(r[0], r[1]) for r in rows}) == len(rows)
    claimed = h.sql("SELECT work_item_id, update_id FROM inbound_change ORDER BY rowid")
    last: dict[int, int] = {}
    for item, update in claimed:  # in update order per item
        assert update > last.get(int(item), 0)
        last[int(item)] = int(update)
    accepted = {
        (int(r[0]), int(r[1]))
        for r in rows
        if r[3] == "accepted" and str(r[4]).startswith("decide:")
    }
    sources = []
    for (detail,) in h.sql("SELECT detail FROM run_activity"):
        source = (detail if isinstance(detail, dict) else json.loads(detail)).get("source")
        if source:
            sources.append((int(source["board_item"]), int(source["update"])))
    # the platform recorded exactly one command per accepted board change, and none twice
    assert sorted(sources) == sorted(accepted)
