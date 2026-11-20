"""Shared wiring for orchestration integration and scenario tests (T007).

A template database is migrated and the real ``adlc-specs/`` registered once per session; each
test gets a fresh copy of the file, so append-only tables never need cleaning. ``Harness``
wires the orchestrator with stubs and a controllable clock.
"""

import itertools
import shutil
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text

from adlc.agents.catalogue import AgentCatalogue, load_catalogues
from adlc.agents.gateway import ModelGateway
from adlc.agents.knowledge import KnowledgeCaller
from adlc.agents.reviewer import RuntimeReviewer
from adlc.agents.runner import RuntimeAgentRunner, RuntimeDeps
from adlc.agents.wiring import build_runtime, reviewer_ids
from adlc.config.settings import DEFAULT_AGENT_LIMITS, AgentLimit
from adlc.orchestration import routing
from adlc.orchestration.engine import EngineConfig
from adlc.orchestration.interfaces import PolicyEngine
from adlc.orchestration.router import FaultHook
from adlc.orchestration.service import Actor
from adlc.orchestration.store import RunRow
from adlc.orchestration.stubs import StubAgent, StubPolicy, StubReviewer
from adlc.orchestration.worker import Orchestrator, build_orchestrator
from adlc.policy.factory import build_policy_engine
from adlc.policy.synthetic import load_synthetic_artifacts
from adlc.spec_toolkit.register import register
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.db import REPO_ROOT, PlatformDatabase, alembic

SPECS = REPO_ROOT / "adlc-specs"
SYNTHETIC = REPO_ROOT / "data" / "synthetic"
DEADLETTER_ROLE = "adlc_coe"
_counter = itertools.count(1)


def build_template(db: PlatformDatabase) -> PlatformDatabase:
    alembic(db, "upgrade", "head")
    engine = db.engine()
    try:
        register(SPECS, engine)
    finally:
        engine.dispose()
    return db


@contextmanager
def fresh_database(db: PlatformDatabase) -> Iterator[PlatformDatabase]:
    """A copy of the template for one test; its folder is removed afterwards."""
    folder = Path(tempfile.mkdtemp(prefix=f"orch_{next(_counter)}_"))
    try:
        yield db.copy_to(folder / "adlc.db")
    finally:
        shutil.rmtree(folder, ignore_errors=True)


class FakeClock:
    """Starts at real time and moves only when told (timers become deterministic)."""

    def __init__(self) -> None:
        self.current = datetime.now(UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


# One account per role keeps "approver differs from proposer" honest (spec assumption).
def person(role: str, *more: str) -> Actor:
    return Actor(f"{role}-person", frozenset({role, *more}))


@dataclass
class Harness:
    db: PlatformDatabase
    app: Engine
    owner: Engine
    clock: FakeClock
    agent: StubAgent
    reviewer: StubReviewer
    policy: Any  # StubPolicy when a test scripts answers, otherwise the real CelPolicyEngine
    orch: Orchestrator
    runtime: RuntimeDeps | None = None  # 006
    approvers: dict[str, list[Actor]] = field(default_factory=dict)

    @property
    def service(self) -> Any:
        return self.orch.service

    def drain(self) -> int:
        return self.orch.drain()

    def submit(self, name: str = "Claims triage", intake: str = "x" * 250) -> str:
        usecase = self.service.submit_usecase(person("business_owner"), name, intake)
        self.drain()
        return str(usecase)

    def runs(self, usecase: str) -> list[RunRow]:
        return list(self.service.list_runs(usecase))

    def run(self, run_id: str) -> RunRow:
        found = self.service.get_run(run_id)
        assert found is not None, run_id
        return found  # type: ignore[no-any-return]

    def active(self, usecase: str, terminal: str) -> RunRow:
        matches = [
            r for r in self.runs(usecase) if r.terminal_id == terminal and r.state != "closed"
        ]
        assert len(matches) == 1, (terminal, [(r.run_id, r.state) for r in self.runs(usecase)])
        return matches[0]

    def pass_run(self, run_id: str, fields: Mapping[str, Any] | None = None) -> None:
        """Pass with as many distinct approvers as the applicable rule needs.

        Emitted values that are not artifacts (FR-018a) are typed in by the approver: the test's
        ``fields`` first, else a placeholder.
        """
        self.drain()  # 005: an edit's controls are re-run before anyone can pass
        run = self.run(run_id)
        spec = self.orch.runs.entry(run.terminal_id, run.spec_version).spec
        given = dict(fields or {})
        missing = routing.emitted_values(spec, run.artifacts, {"usecase_id": run.usecase_id}, given)
        given.update({name: f"{name} (typed)" for name in missing.missing})
        for _ in range(8):
            run = self.run(run_id)
            if run.state == "closed":
                break
            with self.app.connect() as conn:
                ctx = self.orch.runs.context(conn, run)
            signed = {person for person, _ in ctx.approvals}
            needed = sorted(ctx.required_plus_roles - {r for _, r in ctx.approvals}) + sorted(
                ctx.rule_roles
            )
            actor = next(person(r) for r in needed if person(r).account_name not in signed)
            self.service.decide(actor, run_id, "pass", fields=given)
        self.drain()

    def sql(self, statement: str, **params: Any) -> list[Any]:
        with self.owner.connect() as conn:
            return list(conn.execute(text(statement), params))


def stub_builders(catalogue: AgentCatalogue, reviewers: set[str]) -> AgentCatalogue:
    """The catalogue with every terminal builder as a stub (no prompt, no tools); reviewers keep
    their implementation."""
    return AgentCatalogue(
        {
            aid: a if aid in reviewers else replace(a, implementation="stub", prompt=None, tools=())
            for aid, a in catalogue.agents.items()
        }
    )


@contextmanager
def harness(
    db: PlatformDatabase,
    *,
    agent: StubAgent | None = None,
    reviewer: StubReviewer | None = None,
    policy: StubPolicy | None = None,
    fault: FaultHook | None = None,
    time_scale: float = 1.0,
    synthetic_dir: Path = SYNTHETIC,
    gateway: ModelGateway | None = None,
    agents: AgentCatalogue | None = None,
    limits: Mapping[str, AgentLimit] = DEFAULT_AGENT_LIMITS,
    config: EngineConfig | None = None,
    reviewer_mode: str = "stub",
    tools: Mapping[str, Any] | None = None,
    real_agents: bool = False,
    knowledge_caller: KnowledgeCaller | None = None,
    model_agents: tuple[str, ...] = (),
    tools_client: Any = None,
    tools_token_key: str | None = None,
    pilot_evidence: Any = None,
) -> Iterator[Harness]:
    with fresh_database(db) as fresh:
        app = fresh.engine()
        owner = app  # one database identity
        clock = FakeClock()
        registry = SqlSpecRegistry(app)
        agent = agent or StubAgent()
        if not agent.base:
            agent.base = load_synthetic_artifacts(synthetic_dir)
        reviewer = reviewer or StubReviewer()
        engine_policy: PolicyEngine = policy or build_policy_engine(
            app, registry, clock, synthetic_dir=synthetic_dir, pilot=pilot_evidence
        )
        # 006: stub terminal agents run through the runtime (FR-024); tests script models with
        # a FakeGateway and switch agents to implementation: model with ``agents``. Since 008 the
        # registered T0-T2 agents are model agents: unless ``real_agents`` (or ``agents``) is
        # given, every terminal builder runs as a stub, as the 003-007 suites expect.
        if agents is None and not real_agents:
            registered = load_catalogues(registry, "default")[1]
            agents = stub_builders(registered, reviewer_ids(app))
            # 011: the named agents stay the registered model agents (prompt and tools)
            agents = AgentCatalogue(
                {
                    aid: registered.agents[aid] if aid in model_agents else a
                    for aid, a in agents.agents.items()
                }
            )
        runtime = build_runtime(
            app,
            registry,
            engine_policy,
            clock,
            profile="default",
            keys={},
            reviewer_mode="stub",
            spec_dir=SPECS,
            limits=limits,
            gateway=gateway,
            agents=agents,
            check_keys=False,
            tools=tools,
            knowledge_caller=knowledge_caller,
            tools_client=tools_client,
            tools_token_key=tools_token_key,
        )
        orch = build_orchestrator(
            app,
            registry,
            engine_policy,
            RuntimeAgentRunner(runtime, agent),
            RuntimeReviewer(runtime, reviewer, reviewer_mode),
            clock,
            deadletter_role=DEADLETTER_ROLE,
            config=config or EngineConfig(time_scale=time_scale),
            fault=fault,
            worker_id="test-worker",
        )
        try:
            yield Harness(fresh, app, owner, clock, agent, reviewer, engine_policy, orch, runtime)
        finally:
            app.dispose()
