"""012 T023 (US3; FR-003, FR-006, FR-007; SC-002, SC-004): the T8 operations agent reports a
review period from the recorded reading; the model swap lowers answer quality below T4's measured
baseline, the declared monitor raises one drift event with the measured values, and T9 opens."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text

from adlc.orchestration.monitors import MonitorEvaluator
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.acting import acting
from tests.support.acting_scripts import Operations
from tests.support.fake_pilot import SYNTHETIC_CANDIDATE, FakePilot, with_candidate
from tests.support.orchestration import Harness
from tests.support.pg import PlatformDatabase

T8 = "t8-operations-agent"


def _pilot() -> FakePilot:
    fake = with_candidate(FakePilot(), "test")  # T3 (stub) left the candidate in dev and test
    fake.hosts["prod-sim"].stable = SYNTHETIC_CANDIDATE  # T7 (stub) released it
    return fake


def to_t8(h: Harness) -> tuple[str, Any]:
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "low"})
    for terminal in ("T1", "T2", "T3", "T4", "T5", "T6", "T7"):
        run = h.active(usecase, terminal)
        h.drain()
        h.pass_run(run.run_id)
    return usecase, h.active(usecase, "T8")


def record_t4_harness(h: Harness, usecase: str, accuracy: float = 0.97) -> None:
    """T4's recorded harness result for the candidate, as the T4 agent's tool call leaves it (the
    baseline is built from it; feature 011 covers the T4 agent itself)."""
    run = f"{usecase}/T4/run-1"
    result = json.dumps({"catalogue": {"task_success_rate": accuracy}, "dataset": {"id": "golden"}})
    with h.app.begin() as conn:
        call = conn.execute(
            text(
                "INSERT INTO tools.tool_call (run_id, usecase_id, terminal_id, attempt, step, "
                "tool, server, scope, arguments_sha256, outcome, reason, duration_ms, at) VALUES "
                "(:r, :u, 'T4', 1, 1, 'harness_run', 'harness', 'run', :h, 'ok', '', 5, now()) "
                "RETURNING tool_call_id"
            ),
            {"r": run, "u": usecase, "h": "sha256:" + "0" * 64},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO tools.tool_result (tool_call_id, run_id, usecase_id, terminal_id, kind, "
                "package_hash, result, result_sha256, at) VALUES (:c, :r, :u, 'T4', 'harness', :p, "
                "CAST(:res AS jsonb), :h, now())"
            ),
            {
                "c": call,
                "r": run,
                "u": usecase,
                "p": SYNTHETIC_CANDIDATE,
                "res": result,
                "h": "sha256:" + "1" * 64,
            },
        )


def _events(h: Harness, usecase: str) -> list[tuple[str, Any]]:
    with h.app.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT event_type, payload FROM events.outbox_event WHERE usecase_id = :u "
                "AND event_type LIKE '%.event.%' ORDER BY next_attempt_at"
            ),
            {"u": usecase},
        ).all()
    return [(str(t), p if isinstance(p, dict) else json.loads(p)) for t, p in rows]


def test_review_period_then_the_model_swap_raises_drift(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    fake = _pilot()
    with acting(orch_template, {T8: Operations().script()}, (T8,), tmp_path, fake) as a:
        usecase, run = to_t8(a.h)
        record_t4_harness(a.h, usecase)  # baseline 0.97, tolerance 0.05 (T4 spec)
        a.h.drain()
        run = a.h.run(run.run_id)
        decisions = {c["id"]: c for c in run.control_results}
        assert decisions["CTL-T8-05"]["passed"] and not decisions["CTL-T8-05"]["synthetic"]
        assert decisions["CTL-T8-06"]["passed"] and not decisions["CTL-T8-06"]["synthetic"]

        monitors = MonitorEvaluator(
            a.h.app, SqlSpecRegistry(a.h.app), a.h.orch.runs.policy, a.h.service, timedelta(0)
        )
        assert monitors.tick() == 0  # quality at the baseline: nothing fires
        fake.traffic["routing_accuracy"] = 0.6  # the model swap
        assert monitors.tick() == 1
        assert monitors.tick() == 0  # the same breach episode
        drift = [p for t, p in _events(a.h, usecase) if t == "T8.event.drift"]
        assert len(drift) == 1
        assert drift[0]["monitor_id"] == "MON-04" and drift[0]["raised_by"] == "monitor"
        assert "0.6" in json.dumps(drift[0]["measured"])  # the measured value travels with it
        a.h.drain()
        assert a.h.active(usecase, "T9").trigger_event_type == "T8.event.drift"


def test_a_copied_health_value_that_differs_fails(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    operations = Operations()

    def inflated(messages: Any) -> str:
        found = json.loads(operations.answer(messages))
        found["artifacts"]["operating_health_report"][0]["actual"] = 0.999
        return json.dumps(found)

    script = operations.script()[:-1] + [inflated] * 4
    with acting(orch_template, {T8: script}, (T8,), tmp_path, _pilot()) as a:
        _, run = to_t8(a.h)
        a.h.drain()
        failed = {
            c["id"]: c["reason"] for c in a.h.run(run.run_id).control_results if not c["passed"]
        }
        assert "is not the recorded" in failed.get("CTL-T8-05", ""), failed
