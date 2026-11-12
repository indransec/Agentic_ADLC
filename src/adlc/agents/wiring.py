"""Build the agent runtime for the orchestrator process and the test harness (006 T028)."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine, text

from adlc.agents.catalogue import AgentCatalogue, load_catalogues
from adlc.agents.citations import SqlRetrievalLog
from adlc.agents.cost import CostAlerts
from adlc.agents.gateway import LiteLLMTransport, ModelGateway, RoutingGateway
from adlc.agents.knowledge import KnowledgeCaller, McpCaller, knowledge_tools
from adlc.agents.mcp_tools import BoundValues, McpClient, McpClientLike, mcp_tools
from adlc.agents.prompts import SpecTexts, SqlSpecTexts
from adlc.agents.runner import RuntimeDeps
from adlc.agents.startup import check_knowledge_token, check_model_keys
from adlc.agents.store import SqlCallRecorder
from adlc.agents.tool_records import SqlToolRecords
from adlc.agents.tools import Tool, ToolGate
from adlc.config.settings import DEFAULT_AGENT_LIMITS, AgentLimit, AgentLimitOverride
from adlc.orchestration.interfaces import Clock, PolicyEngine
from adlc.policy.evidence import EvidenceProvider, SqlEvidenceProvider
from adlc.spec_toolkit.registry import SpecRegistry
from adlc.tools.registry import Registry


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
    knowledge_url: str | None = None,
    knowledge_token: str | None = None,
    knowledge_caller: KnowledgeCaller | None = None,
    tool_urls: Mapping[str, str] | None = None,
    tools_token_key: str | None = None,
    tools_timeout_s: float = 120.0,
    tools_client: McpClientLike | None = None,
    bound_evidence: EvidenceProvider | None = None,
) -> RuntimeDeps:
    """``knowledge_caller`` replaces the MCP client (tests); otherwise knowledge tools call
    ``knowledge_url`` with ``knowledge_token`` (008 research R-02, R-12)."""
    models, registered_agents = load_catalogues(registry, profile)
    agents = agents or registered_agents
    if check_keys:
        check_model_keys(models, agents, keys, reviewer_ids(engine), reviewer_mode)
        # A test caller stands in for the server and its token.
        check_knowledge_token(agents, knowledge_token or ("caller" if knowledge_caller else None))
    retrievals = SqlRetrievalLog(engine, clock)
    caller = knowledge_caller or (
        McpCaller(knowledge_url, knowledge_token) if knowledge_url and knowledge_token else None
    )
    grounding = {} if caller is None else knowledge_tools(agents, caller, retrievals)
    # 010: tools on the tools and pilot-bridge MCP servers, with run tokens and records.
    acting = _mcp_tools(
        engine,
        registry,
        clock,
        agents,
        tool_urls,
        tools_token_key,
        tools_timeout_s,
        tools_client,
        bound_evidence,
    )
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
        tools=ToolGate(policy, {**grounding, **acting, **(tools or {})}),
        retrievals=retrievals,
    )


def _mcp_tools(
    engine: Engine,
    registry: SpecRegistry,
    clock: Clock,
    agents: AgentCatalogue,
    urls: Mapping[str, str] | None,
    key: str | None,
    timeout_s: float,
    client: McpClientLike | None,
    evidence: EvidenceProvider | None,
) -> dict[str, Tool]:
    entry = registry.catalogue("mcp_servers")
    if key is None or entry is None:
        return {}
    servers = Registry.from_content(entry.content)
    return mcp_tools(
        agents,
        servers,
        client or McpClient(urls or {}, timeout_s),
        key,
        BoundValues(evidence or SqlEvidenceProvider(engine, registry, clock), servers.bound_values),
        SqlToolRecords(engine, clock),
    )
