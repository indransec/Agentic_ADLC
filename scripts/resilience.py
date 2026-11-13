"""Resilience checks on the running demo stack (feature 014, SA §21, research R-06;
``make resilience``, demo environment only).

1. Restart mid-run: a use case's first run is building when the orchestrator container is killed;
   after it starts again the run continues to the people, once (no duplicate transition).
2. Duplicate delivery: a processed routing event is offered again; the router skips it (one run).
3. Dead letter: the orchestrator restarts with ``ADLC_ROUTE_FAULT`` for the next routing event; it
   is retried and dead-lettered; without the fault, the CoE re-queues it; it is delivered and the
   re-queue is recorded.

The script acts as people through the service operations (application database identity) and
uses the owner identity only to offer an event again. It prints each check's evidence.

    uv run python -m scripts.resilience
"""

import os
import subprocess
import sys
import time
from collections.abc import Callable

from dotenv import load_dotenv
from sqlalchemy import Engine, text

from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import OrchestratorSettings
from adlc.db.engine import app_engine, owner_engine
from adlc.orchestration.interfaces import SystemClock
from adlc.orchestration.service import Actor, OrchestratorService
from adlc.orchestration.stubs import StubAgent, StubPolicy, StubReviewer
from adlc.orchestration.worker import build_orchestrator
from adlc.spec_toolkit.registry import SqlSpecRegistry

COMPOSE = ["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env"]
INTAKE = (
    "Resilience check: the IT service desk wants an assistant that proposes a category and a "
    "resolver group for each new ticket so analysts route faster; analysts keep every decision."
)
TIMEOUT_S = 600
NEEDS_PEOPLE = ("awaiting_sign_off", "awaiting_clarification", "escalated", "blocked")


def compose(*args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run([*COMPOSE, *args], check=True, env={**os.environ, **(env or {})})  # noqa: S603


def wait(what: str, ready: Callable[[], bool]) -> None:
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        if ready():
            return
        time.sleep(2)
    raise SystemExit(f"resilience: timed out waiting for {what}")


def scalar(engine: Engine, sql: str, **params: object) -> object:
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def person(role: str) -> Actor:
    return Actor(f"{role}-person", frozenset({role}))


def main() -> int:
    load_dotenv()
    settings = load_settings_or_exit(OrchestratorSettings)
    if settings.env != "demo":
        raise SystemExit("resilience: refused outside ADLC_ENV=demo")
    app, owner = app_engine(settings), owner_engine(settings)
    orchestrator = build_orchestrator(  # the service only; the stack's container advances runs
        app,
        SqlSpecRegistry(app),
        StubPolicy(),
        StubAgent(),
        StubReviewer(),
        SystemClock(),
        deadletter_role=settings.deadletter_role,
        worker_id="resilience",
    )
    service: OrchestratorService = orchestrator.service
    usecase = service.submit_usecase(person("business_owner"), "Resilience check", INTAKE)
    t0 = f"{usecase}/T0/run-1"
    state = "SELECT state FROM run.terminal_run WHERE run_id = :r"

    # 1. restart mid-run
    wait("T0 building", lambda: scalar(app, state, r=t0) == "building")
    compose("kill", "orchestrator")
    compose("start", "orchestrator")
    wait("T0 back with people", lambda: scalar(app, state, r=t0) in NEEDS_PEOPLE)
    duplicates = scalar(
        app,
        "SELECT count(*) - count(DISTINCT (from_state, to_state, at)) FROM run.run_transition "
        "WHERE run_id = :r",
        r=t0,
    )
    print(
        f"PASS restart mid-run: {t0} reached {scalar(app, state, r=t0)}; "
        f"duplicate transitions: {duplicates}"
    )
    if duplicates:
        return 1

    # 2. duplicate delivery
    event = scalar(
        app,
        "SELECT event_id FROM events.outbox_event WHERE usecase_id = :u "
        "AND processed_at IS NOT NULL "
        "ORDER BY created_at LIMIT 1",
        u=usecase,
    )
    with owner.begin() as conn:
        conn.execute(
            text(
                "UPDATE events.outbox_event SET processed_at = NULL, next_attempt_at = now() "
                "WHERE event_id = :e"
            ),
            {"e": event},
        )
    time.sleep(10)
    runs = scalar(
        app,
        "SELECT count(*) FROM run.terminal_run WHERE usecase_id = :u AND terminal_id = 'T0'",
        u=usecase,
    )
    print(
        f"{'PASS' if runs == 1 else 'FAIL'} duplicate delivery: event {event} offered again; "
        f"T0 runs: {runs}"
    )
    if runs != 1:
        return 1

    # 3. dead letter and re-queue
    fault = "T0.pass"  # the next routing event of this use case
    compose("up", "-d", "--no-deps", "orchestrator", env={"ADLC_ROUTE_FAULT": fault})
    wait("T0 back with people", lambda: scalar(app, state, r=t0) == "awaiting_sign_off")
    service.decide(
        person("business_owner"), t0, "pass", reason="resilience check", fields={"risk_tier": "low"}
    )
    dead = (
        "SELECT event_id FROM events.outbox_event WHERE usecase_id = :u AND event_type = :t "
        "AND dead_lettered_at IS NOT NULL"
    )
    wait("the dead letter", lambda: scalar(app, dead, u=usecase, t=fault) is not None)
    event = scalar(app, dead, u=usecase, t=fault)
    compose("up", "-d", "--no-deps", "orchestrator", env={"ADLC_ROUTE_FAULT": ""})
    service.requeue(person(settings.deadletter_role), event)  # type: ignore[arg-type]
    wait(
        "T1 opened",
        lambda: (
            scalar(
                app,
                "SELECT count(*) FROM run.terminal_run WHERE usecase_id = :u "
                "AND terminal_id = 'T1'",
                u=usecase,
            )
            == 1
        ),
    )
    requeues = scalar(
        app, "SELECT count(*) FROM events.dead_letter_action WHERE event_id = :e", e=event
    )
    print(
        f"PASS dead letter: {event} dead-lettered, re-queued ({requeues} recorded), "
        "delivered (T1 open)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
