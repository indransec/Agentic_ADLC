"""SC-001, SC-002: with a 10-second interval, a board decision is applied and shown within 30 s,
and a platform change is on the board within 15 s, for 95% of changes (T059).

The worker loop's own time is measured; the worst case adds a whole interval of waiting (a change
made just after a round), so p95 latency = interval + p95 round time.
"""

from __future__ import annotations

import time
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast

from adlc.engagement.model import ItemWrite
from adlc.engagement.worker import BoardWorker
from tests.integration.engagement.conftest import MEASUREMENTS
from tests.support.board import Rig, needed_roles
from tests.support.orchestration import Harness

INTERVAL = timedelta(seconds=10)
CASES = 20


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]


def test_latency_at_a_ten_second_interval(h: Harness) -> None:
    rig = Rig(h)
    worker = BoardWorker(
        cast(
            Any,
            SimpleNamespace(
                board=rig.board,
                mapping=rig.mapping,
                inbound=rig.sync,
                projector=rig.projector,
                engine=h.app,
            ),
        ),
        INTERVAL,
    )
    runs = []
    for n in range(CASES):
        usecase = h.submit(f"Case {n}")
        h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
        runs.append(h.active(usecase, "T1").run_id)
    worker.step()
    decision_rounds, platform_rounds = [], []
    for run_id in runs:
        role = needed_roles(h, run_id)[0]
        rig.as_role(role).update(
            rig.item("run", run_id),
            ItemWrite(set={rig.mapping.decision_field: rig.mapping.value_for("pass")}),
        )
        started = time.perf_counter()
        worker.step()  # read the decision, apply it, show the result
        decision_rounds.append(time.perf_counter() - started)
        h.drain()  # the platform moves on (the next terminal opens)
        started = time.perf_counter()
        worker.step()  # show it on the board
        platform_rounds.append(time.perf_counter() - started)
    decision = INTERVAL.total_seconds() + _p95(decision_rounds)
    platform = INTERVAL.total_seconds() + _p95(platform_rounds)
    MEASUREMENTS["SC-001 board decision applied and shown, p95"] = f"{decision:.2f} s"
    MEASUREMENTS["SC-002 platform change on the board, p95"] = f"{platform:.2f} s"
    assert decision < 30 and platform < 15
