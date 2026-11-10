"""``adlc-orchestrator``: run the orchestrator loop, or check its heartbeat (research R-11).

``run`` wires the registered specs and, until features 004 and 006 land, the scriptable stubs
for the policy engine, agents and reviewer. ``health`` exits 0 when a worker beat within
``ADLC_HEARTBEAT_MAX_AGE`` (the Compose healthcheck).
"""

import signal
import sys
import threading
from datetime import UTC, datetime
from types import FrameType

import typer

from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import OrchestratorSettings
from adlc.db.engine import DatabaseUnavailable, app_engine, wait_for_database
from adlc.observability.logging import configure_logging
from adlc.observability.tracing import setup_process_tracing
from adlc.orchestration import store
from adlc.orchestration.engine import EngineConfig
from adlc.orchestration.interfaces import SystemClock
from adlc.orchestration.stubs import StubAgent, StubPolicy, StubReviewer
from adlc.orchestration.worker import build_orchestrator
from adlc.spec_toolkit.registry import SqlSpecRegistry

SERVICE_NAME = "adlc-orchestrator"
app = typer.Typer(add_completion=False, help="Lifecycle orchestrator (feature 003).")


@app.command()
def run() -> None:
    """Deliver events, advance runs and fire timers until stopped (SIGTERM or Ctrl-C)."""
    settings = load_settings_or_exit(OrchestratorSettings)
    configure_logging(settings.log_level)
    engine = app_engine(settings)
    try:
        wait_for_database(engine, settings.db_connect_timeout)
    except DatabaseUnavailable as exc:
        print(f"adlc: {exc}", file=sys.stderr)
        raise typer.Exit(1) from exc
    setup_process_tracing(SERVICE_NAME, settings)
    orchestrator = build_orchestrator(
        engine,
        SqlSpecRegistry(engine),
        StubPolicy(),
        StubAgent(),
        StubReviewer(),
        SystemClock(),
        deadletter_role=settings.deadletter_role,
        config=EngineConfig(time_scale=settings.time_scale, lease=settings.lease),
    )
    stop = threading.Event()

    def _stop(signum: int, frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    orchestrator.run_forever(settings.poll_interval, stop)


@app.command()
def health() -> None:
    """Exit 0 when the heartbeat is fresh, 1 otherwise."""
    settings = load_settings_or_exit(OrchestratorSettings)
    engine = app_engine(settings)
    try:
        with engine.connect() as conn:
            beat = store.last_beat(conn)
    except Exception as exc:  # any failure means unhealthy
        print(f"adlc-orchestrator: unhealthy ({type(exc).__name__})", file=sys.stderr)
        raise typer.Exit(1) from exc
    finally:
        engine.dispose()
    if beat is None or datetime.now(UTC) - beat > settings.heartbeat_max_age:
        print("adlc-orchestrator: unhealthy (no recent heartbeat)", file=sys.stderr)
        raise typer.Exit(1)
    print("adlc-orchestrator: healthy")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
