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
from adlc.identity.accounts import load_accounts
from adlc.identity.catalogue import load_role_ids
from adlc.orchestration import routing
from adlc.orchestration.interfaces import SystemClock
from adlc.orchestration.service import Actor, OrchestratorService
from adlc.orchestration.store import RunRow
from adlc.orchestration.stubs import StubAgent, StubPolicy, StubReviewer
from adlc.orchestration.worker import build_orchestrator
from adlc.spec_toolkit.registry import SqlSpecRegistry

LIFECYCLE = ["T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]
SUBMITTER_ROLE = "business_owner"  # demo script data, not platform code
INTAKE = (
    "Claims handlers spend about twelve minutes triaging each motor claim before it reaches "
    "an assessor. We want an assistant that reads the claim, looks up the policy and history, "
    "and proposes a triage category for the handler to confirm."
)
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
        StubPolicy(),  # only the service is used here; the orchestrator container decides
        StubAgent(),
        StubReviewer(),
        SystemClock(),
        deadletter_role=settings.deadletter_role,
        worker_id="demo-drive",
    )
    service = orch.service
    usecase = service.submit_usecase(_submitter(settings), "Demo: claims triage", INTAKE)
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


def _submitter(settings: OrchestratorSettings) -> Actor:
    """A real account holding the business-owner role of T0's sign-off, when the account file is
    set: the orchestrator checks the submitter against the directory (PRE-T0-02)."""
    if settings.accounts_file is None:
        return person(SUBMITTER_ROLE)
    accounts = load_accounts(
        settings.accounts_file, load_role_ids(settings.role_catalogue), settings.env
    )
    for account in accounts.values():
        if SUBMITTER_ROLE in account.roles:
            return Actor(account.account_name, account.roles)
    raise SystemExit(f"no account in {settings.accounts_file} holds {SUBMITTER_ROLE}")


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
