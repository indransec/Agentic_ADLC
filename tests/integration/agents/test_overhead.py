"""T040: the runtime's own overhead per attempt, excluding model time, is under 200 ms (SC-009).

The fake model answers instantly, so the measured time is the runtime: reading the run, building
and hashing the context pack, validating the output and writing the records."""

import time
from typing import Any

from adlc.agents.fake import reply
from adlc.orchestration import store
from tests.support.lifecycle import walk_to

from .support import GOOD, PRIMARY

ATTEMPTS = 10
BUDGET_MS = 200.0


def test_runtime_overhead(model_harness: Any) -> None:
    h, _ = model_harness({PRIMARY: reply(GOOD)})
    usecase, t1 = walk_to(h, "T1")
    runs = h.orch.runs
    with h.app.connect() as conn:
        run = store.load_run(conn, t1)
        assert run is not None
        context = runs._build_context(conn, run, runs.entry(run.terminal_id, run.spec_version).spec)
    runner = runs.agent
    runner.build(context)  # warm-up: imports, first queries
    started = time.perf_counter()
    for _ in range(ATTEMPTS):
        runner.build(context)
    per_attempt_ms = (time.perf_counter() - started) * 1000 / ATTEMPTS
    assert per_attempt_ms < BUDGET_MS, f"{per_attempt_ms:.0f} ms per attempt"
