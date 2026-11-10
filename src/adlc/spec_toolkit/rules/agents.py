"""L4 rules for the agent runtime catalogues (feature 006, research R-04).

The model catalogue, the agents catalogue and the prompts must agree with each other and with
the terminal specs. No agent, model, terminal or provider name is written here (constitution I).
"""

from collections.abc import Iterator
from typing import Any

from adlc.spec_toolkit.findings import Finding
from adlc.spec_toolkit.rules import REGISTRY, Context
from adlc.spec_toolkit.rules.cross_spec import catalogues
from adlc.spec_toolkit.rules.single_spec import spec

DEFAULT_PROFILE = "default"
MCP_VERB = "mcp"


def _rel(ctx: Context, name: str) -> str:
    loaded = ctx.bundle.catalogues.get(name)
    return loaded.rel if loaded else f"shared/{name}.yaml"


def _usable(ctx: Context, name: str) -> bool:
    loaded = ctx.bundle.catalogues.get(name)
    return loaded is not None and not loaded.parse_failed and not loaded.schema_failed


def _agents(ctx: Context) -> list[tuple[int, dict[str, Any]]]:
    value = ctx.catalogue("agents").get("agents")
    return [(i, a) for i, a in enumerate(value or []) if isinstance(a, dict)]


@REGISTRY.rule(
    "V-27", "L4", "error", "Model catalogue: a default profile; every profile covers every tier"
)
def v27_model_catalogue(ctx: Context) -> Iterator[Finding]:
    if not _usable(ctx, "model_catalogue"):
        return
    cats = catalogues(ctx)
    rel = _rel(ctx, "model_catalogue")
    profiles = ctx.catalogue("model_catalogue").get("profiles") or {}
    if DEFAULT_PROFILE not in profiles:
        yield ctx.finding("V-27", rel, "/profiles", f"profile {DEFAULT_PROFILE!r} is required")
    for name, tiers in profiles.items():
        for tier in sorted(cats.model_tiers - set(tiers)):
            yield ctx.finding("V-27", rel, f"/profiles/{name}", f"tier {tier} has no models")
        for tier, entries in tiers.items():
            if tier not in cats.model_tiers:
                yield ctx.finding(
                    "V-27", rel, f"/profiles/{name}/{tier}", f"model tier {tier} unknown"
                )
            for i, entry in enumerate(entries or []):
                data_class = entry.get("max_data_class")
                if data_class not in cats.data_classes:
                    yield ctx.finding(
                        "V-27",
                        rel,
                        f"/profiles/{name}/{tier}/{i}/max_data_class",
                        f"data class {data_class} unknown",
                    )


@REGISTRY.rule("V-28", "L4", "error", "Terminal agents and reviewers exist in the agents catalogue")
def v28_agents(ctx: Context) -> Iterator[Finding]:
    if not _usable(ctx, "agents"):
        return
    cats = catalogues(ctx)
    agents = {str(a.get("id")): a for _, a in _agents(ctx)}
    for i, agent in _agents(ctx):
        if agent.get("model_tier") not in cats.model_tiers:
            yield ctx.finding(
                "V-28",
                _rel(ctx, "agents"),
                f"/agents/{i}/model_tier",
                f"model tier {agent.get('model_tier')} unknown",
            )
    for loaded in ctx.terminals():
        actors = spec(loaded).get("actors") or {}
        agent_ref = actors.get("agent") or {}
        agent_id = agent_ref.get("id")
        if agent_id not in agents:
            yield ctx.finding(
                "V-28", loaded.rel, "/terminal/actors/agent/id", f"agent {agent_id} not registered"
            )
        elif agents[agent_id].get("model_tier") != agent_ref.get("model_tier"):
            yield ctx.finding(
                "V-28",
                loaded.rel,
                "/terminal/actors/agent/model_tier",
                f"agent {agent_id} is registered with tier "
                f"{agents[agent_id].get('model_tier')}, not {agent_ref.get('model_tier')}",
            )
        reviewer = actors.get("reviewer")
        if reviewer is not None and reviewer not in agents:
            yield ctx.finding(
                "V-28",
                loaded.rel,
                "/terminal/actors/reviewer",
                f"reviewer {reviewer} not registered",
            )


@REGISTRY.rule("V-29", "L4", "error", "Agent prompt references resolve to a prompt file")
def v29_prompts(ctx: Context) -> Iterator[Finding]:
    if not _usable(ctx, "agents"):
        return
    prompts = {
        (str(p.data.get("id")), str(p.data.get("version"))): p.data
        for p in ctx.bundle.prompts.values()
        if isinstance(p.data, dict) and not p.parse_failed
    }
    rel = _rel(ctx, "agents")
    for i, agent in _agents(ctx):
        ref = agent.get("prompt")
        if not isinstance(ref, dict):
            continue  # required for model agents by the schema (S-02)
        key = (str(ref.get("id")), str(ref.get("version")))
        if key not in prompts:
            yield ctx.finding(
                "V-29", rel, f"/agents/{i}/prompt", f"prompt {key[0]}@{key[1]} not found"
            )
        elif prompts[key].get("agent") != agent.get("id"):
            yield ctx.finding(
                "V-29",
                rel,
                f"/agents/{i}/prompt",
                f"prompt {key[0]}@{key[1]} is written for agent {prompts[key].get('agent')}",
            )


@REGISTRY.rule("V-30", "L4", "error", "Agent tool permissions use known verbs or MCP scopes")
def v30_tool_permissions(ctx: Context) -> Iterator[Finding]:
    if not _usable(ctx, "agents"):
        return
    cats = catalogues(ctx)
    rel = _rel(ctx, "agents")
    for i, agent in _agents(ctx):
        for j, binding in enumerate(agent.get("tools") or []):
            permission = str(binding.get("permission"))
            verb, _, resource = permission.partition(":")
            if verb == MCP_VERB:
                server, _, scope = resource.partition(":")
                ok = server in cats.mcp_scopes and scope in cats.mcp_scopes[server]
            else:
                ok = verb in cats.permission_verbs and bool(resource)
            if not ok:
                yield ctx.finding(
                    "V-30",
                    rel,
                    f"/agents/{i}/tools/{j}/permission",
                    f"permission {permission} uses an unknown verb or MCP scope",
                )


@REGISTRY.rule(
    "V-31", "L4", "error", "Data-class resolvers name an existing terminal artifact column"
)
def v31_resolver_sources(ctx: Context) -> Iterator[Finding]:
    if not _usable(ctx, "data_classes"):
        return
    columns: dict[tuple[str, str], set[str]] = {}
    for loaded in ctx.terminals():
        t = spec(loaded)
        terminal = str((t.get("metadata") or {}).get("id"))
        for artifact in (t.get("evidence") or {}).get("artifacts") or []:
            if isinstance(artifact, dict):
                columns[(terminal, str(artifact.get("id")))] = {
                    str(c) for c in artifact.get("columns") or []
                }
    resolvers = ctx.catalogue("data_classes").get("resolvers") or []
    for i, resolver in enumerate(resolvers):
        source = resolver.get("source") if isinstance(resolver, dict) else None
        if source is None:
            continue  # a resolver without a source stays unresolved (fails closed at run time)
        terminal, artifact, column = str(source).split(".")
        if not any(t == terminal for t, _ in columns):
            yield ctx.finding(
                "V-31",
                _rel(ctx, "data_classes"),
                f"/resolvers/{i}/source",
                f"resolver source {source}: terminal {terminal} is not in this spec folder",
                severity="info",
            )
            continue
        if column not in columns.get((terminal, artifact), set()):
            yield ctx.finding(
                "V-31",
                _rel(ctx, "data_classes"),
                f"/resolvers/{i}/source",
                f"resolver source {source} is not a declared artifact column",
            )
