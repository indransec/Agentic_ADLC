"""Build the agent runtime for the orchestrator process and the test harness (006 T028)."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine, text

from adlc.agents.catalogue import AgentCatalogue, load_catalogues
from adlc.agents.cost import CostAlerts
from adlc.agents.gateway import LiteLLMTransport, ModelGateway, RoutingGateway
from adlc.agents.prompts import SpecTexts, SqlSpecTexts
from adlc.agents.runner import RuntimeDeps
from adlc.agents.startup import check_model_keys
from adlc.agents.store import SqlCallRecorder
from adlc.agents.tools import Tool, ToolGate
from adlc.config.settings import DEFAULT_AGENT_LIMITS, AgentLimit, AgentLimitOverride
from adlc.orchestration.interfaces import Clock, PolicyEngine
from adlc.spec_toolkit.registry import SpecRegistry


def reviewer_ids(engine: Engine) -> set[str]:
    """Agents named as reviewers by the active terminal specs."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT DISTINCT spec_json->'terminal'->'actors'->>'reviewer' "
                "FROM spec.spec_registry WHERE status = 'active'"
            )
        ).scalars()
        return {str(r) for r in rows if r}


def build_runtime(
    engine: Engine,
    registry: SpecRegistry,
    policy: PolicyEngine,
    clock: Clock,
    *,
    profile: str,
    keys: Mapping[str, str | None],
    reviewer_mode: str,
    spec_dir: Path,
    limits: Mapping[str, AgentLimit] = DEFAULT_AGENT_LIMITS,
    overrides: Mapping[str, AgentLimitOverride] | None = None,
    corrections: int = 2,
    gateway: ModelGateway | None = None,
    agents: AgentCatalogue | None = None,
    texts: SpecTexts | None = None,
    check_keys: bool = True,
    tools: Mapping[str, Tool] | None = None,
    cost_alert_levels: Sequence[Decimal] = (),
) -> RuntimeDeps:
    models, registered_agents = load_catalogues(registry, profile)
    agents = agents or registered_agents
    if check_keys:
        check_model_keys(models, agents, keys, reviewer_ids(engine), reviewer_mode)
    return RuntimeDeps(
        engine=engine,
        registry=registry,
        models=models,
        agents=agents,
        texts=texts or SqlSpecTexts(engine, spec_dir),
        gateway=gateway
        or RoutingGateway(
            models,
            keys,
            LiteLLMTransport(),
            SqlCallRecorder(engine),
            clock,
            after_record=CostAlerts(engine, cost_alert_levels).check,
        ),
        policy=policy,
        limits=limits,
        overrides=dict(overrides or {}),
        corrections=corrections,
        clock=clock,
        tools=ToolGate(policy, tools or {}),
    )
