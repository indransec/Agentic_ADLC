"""T068: heartbeat, health command, polling, routing latency (SC-003, research R-11)."""

import os
import statistics
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from typer.testing import CliRunner

from adlc.orchestration.__main__ import app
from adlc.orchestration.engine import EngineConfig
from adlc.orchestration.interfaces import SystemClock
from adlc.orchestration.stubs import StubAgent, StubPolicy, StubReviewer
from adlc.orchestration.worker import build_orchestrator
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.db import patched_env
from tests.support.lifecycle import ORDER
from tests.support.orchestration import DEADLETTER_ROLE, Harness, person

runner = CliRunner()


def _env(h: Harness, **extra: str) -> dict[str, str]:
    return {
        **h.db.env,
        "ADLC_DEADLETTER_ROLE": DEADLETTER_ROLE,
        "ADLC_DB_CONNECT_TIMEOUT": "5s",
        **extra,
    }


def test_heartbeat_and_health(h: Harness) -> None:
    with patched_env(_env(h)):
        assert runner.invoke(app, ["health"]).exit_code == 1  # no worker yet
        h.orch.runs.clock = SystemClock()
        h.orch.run_once()
        result = runner.invoke(app, ["health"])
        assert result.exit_code == 0, result.output
    with h.owner.begin() as conn:
        conn.execute(
            text("UPDATE orchestrator_heartbeat SET beat_at = :t"),
            {"t": datetime.now(UTC) - timedelta(hours=1)},
        )
    with patched_env(_env(h)):
        assert runner.invoke(app, ["health"]).exit_code == 1


def test_polling_loop_routing_is_fast(h: Harness) -> None:
    """A live loop over a real clock, polling every second (the ``ADLC_POLL_INTERVAL``
    default): close-to-next-open gap p95 ≤ 2 s (≤ 5 s on CI)."""
    engine = h.db.engine()
    orch = build_orchestrator(
        engine,
        SqlSpecRegistry(engine),
        StubPolicy(),
        StubAgent(),
        StubReviewer(),
        SystemClock(),
        deadletter_role=DEADLETTER_ROLE,
        config=EngineConfig(),
        worker_id="live",
    )
    stop = threading.Event()
    loop = threading.Thread(target=orch.run_forever, args=(timedelta(seconds=1), stop), daemon=True)
    loop.start()
    try:
        gaps: list[float] = []
        for n in range(6):
            usecase = orch.service.submit_usecase(
                person("business_owner"), f"latency {n}", "x" * 250
            )
            for terminal in ORDER:
                run = _wait_for(orch, usecase, terminal)
                _pass(orch, run, terminal)
                closed = orch.service.get_run(run)
                assert closed is not None and closed.closed_at is not None
                if terminal != ORDER[-1]:
                    nxt = orch.service.get_run(
                        _wait_for(orch, usecase, ORDER[ORDER.index(terminal) + 1])
                    )
                    assert nxt is not None
                    gaps.append((nxt.opened_at - closed.closed_at).total_seconds())
    finally:
        stop.set()
        loop.join(timeout=10)
        engine.dispose()
    p95 = statistics.quantiles(gaps, n=20)[18]
    print(f"routing gap over {len(gaps)} closes: p95 {p95:.3f}s, max {max(gaps):.3f}s")
    limit = 5.0 if os.environ.get("CI") else 2.0
    assert p95 <= limit


def _wait_for(orch, usecase: str, terminal: str) -> str:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        for r in orch.service.list_runs(usecase):
            if r.terminal_id == terminal and r.state == "awaiting_sign_off":
                return str(r.run_id)
        time.sleep(0.02)
    pytest.fail(f"{terminal} of {usecase} never reached sign-off")


def _pass(orch, run_id: str, terminal: str) -> None:  # type: ignore[no-untyped-def]
    from adlc.orchestration import routing

    run = orch.service.get_run(run_id)
    spec = orch.runs.entry(run.terminal_id, run.spec_version).spec
    fields = {"risk_tier": "medium"}
    missing = routing.emitted_values(
        spec, run.artifacts, {"usecase_id": run.usecase_id}, fields
    ).missing
    fields.update({m: "typed" for m in missing})
    for _ in range(6):
        current = orch.service.get_run(run_id)
        if current.state == "closed":
            return
        with orch.runs.engine.connect() as conn:
            ctx = orch.runs.context(conn, current)
        signed = {p for p, _ in ctx.approvals}
        roles = sorted(ctx.required_plus_roles - {r for _, r in ctx.approvals}) + sorted(
            ctx.rule_roles
        )
        actor = next(person(r) for r in roles if person(r).account_name not in signed)
        orch.service.decide(actor, run_id, "pass", fields=fields)


def test_now_is_aware() -> None:
    assert SystemClock().now().tzinfo is UTC
    assert datetime.now(UTC) - SystemClock().now() < timedelta(seconds=1)


def test_event_from_another_process_is_polled(h: Harness) -> None:
    """T082: an event another process writes is delivered within the poll interval."""
    engine = h.db.engine()
    orch = build_orchestrator(
        engine,
        SqlSpecRegistry(engine),
        StubPolicy(),
        StubAgent(),
        StubReviewer(),
        SystemClock(),
        deadletter_role=DEADLETTER_ROLE,
        config=EngineConfig(),
        worker_id="poller",
    )
    usecase = orch.service.submit_usecase(person("business_owner"), "poll", "x" * 250)
    stop = threading.Event()
    loop = threading.Thread(
        target=orch.run_forever, args=(timedelta(milliseconds=200), stop), daemon=True
    )
    loop.start()
    try:
        _wait_for(orch, usecase, "T0")
        with h.owner.begin() as conn:  # written outside the loop: only polling can find it
            conn.execute(
                text(
                    "INSERT INTO outbox_event (event_id, event_type, usecase_id, "
                    "correlation_id, payload, next_attempt_at) VALUES (:e, "
                    "'T0.exception', :u, :c, '{}', now())"
                ),
                {"e": uuid.uuid4(), "u": usecase, "c": f"{usecase}/lifecycle"},
            )
        started = time.monotonic()
        _wait_for(orch, usecase, "T1")
        assert time.monotonic() - started < 2.0
    finally:
        stop.set()
        loop.join(timeout=10)
        engine.dispose()
