"""Wiring of ``adlc-replay`` to the environment (008 T029, contracts/replay.md).

The replay runs its own orchestrator worker against the environment's database (``.env``), so it
refuses to start while another worker is active: that worker would advance the replay's runs with
its own models. Stop it first (``docker compose stop orchestrator``).
"""

import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from adlc.agents.catalogue import load_catalogues
from adlc.agents.cost import CostAlerts
from adlc.agents.gateway import LiteLLMTransport, RoutingGateway
from adlc.agents.prompts import SqlSpecTexts
from adlc.agents.replay import (
    AgentReplies,
    RecordingTransport,
    Replayer,
    Report,
    load_references,
    read_recording,
    replay_gateway,
)
from adlc.agents.reviewer import RuntimeReviewer
from adlc.agents.runner import RuntimeAgentRunner
from adlc.agents.store import SqlCallRecorder
from adlc.agents.wiring import build_runtime
from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import OrchestratorSettings
from adlc.db.engine import app_engine
from adlc.identity.accounts import load_accounts
from adlc.identity.catalogue import load_role_ids
from adlc.observability.tracing import setup_process_tracing
from adlc.orchestration import store
from adlc.orchestration.engine import EngineConfig
from adlc.orchestration.interfaces import SystemClock
from adlc.orchestration.service import Actor
from adlc.orchestration.stubs import StubAgent, StubReviewer
from adlc.orchestration.worker import build_orchestrator
from adlc.policy.directory import AccountFileDirectory
from adlc.policy.factory import build_policy_engine
from adlc.policy.pilot_evidence import PilotEvidence
from adlc.policy.synthetic import load_synthetic_artifacts
from adlc.spec_toolkit.registry import SqlSpecRegistry
from adlc.tools.client import McpClient

SERVICE_NAME = "adlc-replay"


class SwitchGateway:
    """Lets each use case replay its own recording through one runtime."""

    current: Any = None

    def complete(self, request: Any) -> Any:
        return self.current.complete(request)


class MixedGateway:
    """011: agents with a recording replay it; the others call the live model (to run later
    terminals live after earlier ones from their recordings)."""

    def __init__(self, replies: AgentReplies, recorded: Any, live: Any) -> None:
        self.replies, self.recorded, self.live = replies, recorded, live

    def complete(self, request: Any) -> Any:
        agent = self.replies.agent_of(request.messages)
        if agent is not None and self.replies.replies.get(agent):
            return self.recorded.complete(request)
        return self.live.complete(request)


def _fail(message: str) -> typer.Exit:
    print(f"adlc-replay: {message}", file=sys.stderr)
    return typer.Exit(2)


def run_cli(
    reference_set: Path,
    only: Sequence[str],
    *,
    profile: str | None,
    record: Path | None,
    recording: Path | None,
    live_rest: bool = False,
) -> Report:
    settings = load_settings_or_exit(OrchestratorSettings)
    provider = setup_process_tracing(SERVICE_NAME, settings)  # spans go to the same collector
    engine = app_engine(settings)
    with engine.connect() as conn:
        beat = store.last_beat(conn)
    if beat is not None and datetime.now(UTC) - beat < settings.heartbeat_max_age:
        raise _fail(
            "an orchestrator worker is running; stop it first (it would run these use cases)"
        )
    if settings.accounts_file is None:
        raise _fail("ADLC_ACCOUNTS_FILE is needed: the replay acts as the people in it")
    accounts = load_accounts(
        settings.accounts_file, load_role_ids(settings.role_catalogue), settings.env
    )
    by_role: dict[str, list[Actor]] = {}
    for account in sorted(accounts.values(), key=lambda a: (len(a.roles), a.account_name)):
        for role in sorted(account.roles):  # single-role accounts first
            by_role.setdefault(role, []).append(Actor(account.account_name, account.roles))

    def people(role: str) -> list[Actor]:
        if role not in by_role:
            raise _fail(f"no account in the account file holds role {role}")
        return by_role[role]

    references = load_references(reference_set, only)
    if not references:
        raise _fail(f"no reference use cases in {reference_set}")
    registry = SqlSpecRegistry(engine)
    clock = SystemClock()
    key = None if settings.tools_token_key is None else settings.tools_token_key.get_secret_value()
    policy = build_policy_engine(
        engine,
        registry,
        clock,
        synthetic_dir=settings.synthetic_dir,
        directory=AccountFileDirectory(
            settings.accounts_file, settings.role_catalogue, settings.env
        ),
        # 011: the acting terminals' evidence (env, template) from the pilot through the bridge
        pilot=None
        if key is None
        else PilotEvidence(McpClient({"bridge": settings.pilot_bridge_url}, 30), key),
    )
    chosen = profile or settings.model_profile
    models, agents = load_catalogues(registry, chosen)
    texts = SqlSpecTexts(engine, settings.spec_dir)
    prompts = {a.id: texts.prompt(*a.prompt).body for a in agents.agents.values() if a.prompt}
    switch = SwitchGateway()
    recorder = SqlCallRecorder(engine)
    capture: RecordingTransport | None = None
    live_gateway: Any = None
    live = recording is None or live_rest
    if live:
        capture = RecordingTransport(LiteLLMTransport(), AgentReplies(prompts, {}))
        live_gateway = RoutingGateway(
            models,
            settings.provider_keys(),
            capture,
            recorder,
            clock,
            after_record=CostAlerts(engine, settings.cost_alert_levels).check,
        )
        switch.current = live_gateway
    token = settings.knowledge_token
    runtime = build_runtime(
        engine,
        registry,
        policy,
        clock,
        profile=chosen,
        keys=settings.provider_keys(),
        reviewer_mode=settings.reviewer_mode,
        spec_dir=settings.spec_dir,
        limits=settings.agent_limits,
        overrides=settings.agent_limit_overrides,
        corrections=settings.agent_corrections,
        gateway=switch,
        check_keys=live,
        knowledge_url=settings.knowledge_url,
        knowledge_token=None if token is None else token.get_secret_value(),
        tool_urls={"tools": settings.tools_url, "bridge": settings.pilot_bridge_url},
        tools_token_key=key,
        tools_timeout_s=settings.tools_timeout_s,
    )
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
        config=EngineConfig(time_scale=settings.time_scale, lease=settings.lease),
        worker_id="adlc-replay",
    )
    replayer = Replayer(orchestrator.service, orchestrator.runs, orchestrator.drain, people)
    results = []
    for ref in references:
        if recording is not None:
            replies = AgentReplies(prompts, read_recording(recording / ref.id))
            recorded = replay_gateway(models, replies, recorder)
            switch.current = (
                MixedGateway(replies, recorded, live_gateway) if live_rest else recorded
            )
        results.append(replayer.run(ref))
        if capture is not None and record is not None:
            capture.save(record / ref.id)
    provider.force_flush()
    mode = "live" if recording is None else ("recording+live" if live_rest else "recording")
    return Report(mode, chosen, results)
