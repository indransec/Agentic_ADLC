"""SC-006: reconciling 50 use cases with 10 injected differences reports and corrects all 10;
a second run reports none; under a minute (T057)."""

from __future__ import annotations

import time

from adlc.engagement.model import ItemWrite
from adlc.engagement.reconcile import Reconciler
from tests.integration.engagement.conftest import MEASUREMENTS
from tests.support.board import Rig
from tests.support.orchestration import DEADLETTER_ROLE, Harness, person


def test_fifty_use_cases_ten_differences(h: Harness) -> None:
    rig = Rig(h)
    usecases = [h.submit(f"Case {n}") for n in range(50)]
    rig.cycle(rounds=1)
    sub_stage = rig.mapping.field("usecase", "sub_stage")
    for usecase in usecases[:10]:
        rig.board.update(rig.item("usecase", usecase), ItemWrite(set={sub_stage: "tampered"}))
    reconciler = Reconciler(h.app, rig.projector, rig.board, rig.mapping, h.clock, DEADLETTER_ROLE)
    started = time.perf_counter()
    first = reconciler.reconcile(person(DEADLETTER_ROLE))
    seconds = time.perf_counter() - started
    MEASUREMENTS["SC-006 reconcile 50 use cases"] = f"{seconds:.2f} s"
    corrected = {d["object_id"] for d in first["differences"] if d["action"] == "corrected"}
    assert corrected == set(usecases[:10])
    assert reconciler.reconcile(person(DEADLETTER_ROLE))["differences"] == []
    assert seconds < 60
