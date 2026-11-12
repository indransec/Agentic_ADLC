"""``adlc-orchestrator``: run the orchestrator loop, or check its heartbeat (research R-11).

``run`` wires the registered specs, the policy engine (feature 004, with labelled synthetic
evidence) and, until feature 006 lands, the stub agent (starting from synthetic artifacts) and
stub reviewer. ``health`` exits 0 when a worker beat within
``ADLC_HEARTBEAT_MAX_AGE`` (the Compose healthcheck).
"""

import signal
import sys
import threading
from datetime import UTC, datetime
from types import FrameType

import typer

from adlc.agents.catalogue import UnknownProfile
from adlc.agents.reviewer import RuntimeReviewer
from adlc.agents.runner import RuntimeAgentRunner
from adlc.agents.startup import MissingKnowledgeToken, MissingModelKey
from adlc.agents.wiring import build_runtime
from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import OrchestratorSettings
from adlc.db.engine import DatabaseUnavailable, app_engine, wait_for_database
from adlc.observability.logging import configure_logging
from adlc.observability.tracing import setup_process_tracing
from adlc.orchestration import store
from adlc.orchestration.engine import EngineConfig
from adlc.orchestration.interfaces import SystemClock
from adlc.orchestration.stubs import StubAgent, StubReviewer
from adlc.orchestration.worker import build_orchestrator
from adlc.policy.directory import AccountFileDirectory
from adlc.policy.factory import build_policy_engine
from adlc.policy.pilot_evidence import PilotEvidence
from adlc.policy.synthetic import load_synthetic_artifacts
from adlc.spec_toolkit.registry import SqlSpecRegistry
from adlc.tools.client import McpClient

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
    registry = SqlSpecRegistry(engine)
    clock = SystemClock()
    directory = (
        AccountFileDirectory(settings.accounts_file, settings.role_catalogue, settings.env)
        if settings.accounts_file
        else None
    )
    key = None if settings.tools_token_key is None else settings.tools_token_key.get_secret_value()
    pilot = (
        None
        if key is None
        else PilotEvidence(McpClient({"bridge": settings.pilot_bridge_url}, 30), key)
    )
    policy = build_policy_engine(
        engine,
        registry,
        clock,
        synthetic_dir=settings.synthetic_dir,
        directory=directory,
        pilot=pilot,
    )
    try:
        runtime = build_runtime(
            engine,
            registry,
            policy,
            clock,
            profile=settings.model_profile,
            keys=settings.provider_keys(),
            reviewer_mode=settings.reviewer_mode,
            spec_dir=settings.spec_dir,
            limits=settings.agent_limits,
            overrides=settings.agent_limit_overrides,
            corrections=settings.agent_corrections,
            cost_alert_levels=settings.cost_alert_levels,
            knowledge_url=settings.knowledge_url,
            knowledge_token=None
            if settings.knowledge_token is None
            else settings.knowledge_token.get_secret_value(),
            tool_urls={"tools": settings.tools_url, "bridge": settings.pilot_bridge_url},
            tools_token_key=key,
            tools_timeout_s=settings.tools_timeout_s,
        )
    except (MissingModelKey, MissingKnowledgeToken, UnknownProfile) as exc:
        print(f"adlc: configuration error\n  {exc}", file=sys.stderr)
        raise typer.Exit(2) from exc
    orchestrator = build_orchestrator(
        engine,
        registry,
        policy,
        RuntimeAgentRunner(
            runtime, StubAgent(base=load_synthetic_artifacts(settings.synthetic_dir))
        ),
        RuntimeReviewer(runtime, StubReviewer(), settings.reviewer_mode),
        clock,
        deadletter_role=settings.deadletter_role,
        config=EngineConfig(
            time_scale=settings.time_scale,
            lease=settings.lease,
            model_outage_limit=settings.model_outage_limit,
        ),
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
