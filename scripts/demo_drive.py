"""Drive the live stack through the happy path (003 quickstart §4).

Until feature 007 exposes the service operations over HTTP, this script calls
``OrchestratorService`` directly with the application database identity, acting as one
synthetic person per role (``<role>-person``), the same way the scenario tests do. The running
``orchestrator`` container does the routing; the script only submits and decides, then prints
every run and the gap between a close and the next open (SC-003).

    uv run python -m scripts.demo_drive            # reads .env for the database settings
"""

import sys
import time
from datetime import timedelta

from dotenv import load_dotenv

from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import OrchestratorSettings
from adlc.db.engine import app_engine
from adlc.orchestration import routing
from adlc.orchestration.interfaces import SystemClock
from adlc.orchestration.service import Actor, OrchestratorService
from adlc.orchestration.store import RunRow
from adlc.orchestration.stubs import StubAgent, StubPolicy, StubReviewer
from adlc.orchestration.worker import build_orchestrator
from adlc.spec_toolkit.registry import SqlSpecRegistry

LIFECYCLE = ["T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]
WAIT = timedelta(seconds=30)


def person(role: str) -> Actor:
    return Actor(f"{role}-person", frozenset({role}))


def main() -> int:
    load_dotenv()
    settings = load_settings_or_exit(OrchestratorSettings)
    engine = app_engine(settings)
    # Only the service is used here; the orchestrator container routes and advances runs.
    orch = build_orchestrator(
        engine,
        SqlSpecRegistry(engine),
        StubPolicy(),
        StubAgent(),
        StubReviewer(),
        SystemClock(),
        deadletter_role=settings.deadletter_role,
        worker_id="demo-drive",
    )
    service = orch.service
    usecase = service.submit_usecase(person("business_owner"), "Demo: claims triage", "x" * 250)
    print(f"submitted {usecase}")
    for terminal in LIFECYCLE:
        run_id = _await_sign_off(orch, usecase, terminal)
        run = _run(service, run_id)
        spec = orch.runs.entry(run.terminal_id, run.spec_version).spec
        fields = {"risk_tier": "medium"}
        emitted = routing.emitted_values(spec, run.artifacts, {"usecase_id": usecase}, fields)
        fields.update({name: f"{name} (demo)" for name in emitted.missing})
        while (current := _run(service, run_id)).state != "closed":
            with engine.connect() as conn:
                ctx = orch.runs.context(conn, current)
            signed = {p for p, _ in ctx.approvals}
            roles = sorted(ctx.required_plus_roles - {r for _, r in ctx.approvals})
            roles += sorted(ctx.rule_roles)
            actor = next(person(r) for r in roles if person(r).account_name not in signed)
            service.decide(actor, run_id, "pass", fields=fields)
        print(f"  {run_id}: pass")
    runs = service.list_runs(usecase)
    print(f"\n{'run':<22} {'state':<18} {'status':<10} gap to next open")
    for current, nxt in zip(runs, [*runs[1:], None], strict=True):
        gap = ""
        if nxt is not None and current.closed_at is not None:
            gap = f"{(nxt.opened_at - current.closed_at).total_seconds():.3f}s"
        print(f"{current.run_id:<22} {current.state:<18} {current.final_status or '':<10} {gap}")
    engine.dispose()
    return 0


def _run(service: OrchestratorService, run_id: str) -> RunRow:
    run = service.get_run(run_id)
    if run is None:
        raise SystemExit(f"run {run_id} disappeared")
    return run


def _await_sign_off(orch, usecase: str, terminal: str) -> str:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + WAIT.total_seconds()
    while time.monotonic() < deadline:
        for run in orch.service.list_runs(usecase):
            if run.terminal_id == terminal and run.state == "awaiting_sign_off":
                return str(run.run_id)
        time.sleep(0.2)
    print(f"{terminal} did not reach sign-off within {WAIT}; is the orchestrator running?")
    sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
