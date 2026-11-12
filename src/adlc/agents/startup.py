"""Start-up check for model keys (006 FR-018, research R-16).

A process that will run model agents, or the model reviewer, refuses to start when the selected
catalogue profile has no keyed model for a tier it needs, instead of discovering it mid-run.
"""

from collections.abc import Iterable, Mapping

from adlc.agents.catalogue import AgentCatalogue, ModelCatalogue


class MissingModelKey(Exception):
    pass


def needed_tiers(
    agents: AgentCatalogue, reviewer_ids: Iterable[str], reviewer_mode: str
) -> dict[str, list[str]]:
    """Tier to the model agents that need it; reviewers count only in ``model`` mode."""
    reviewers = set(reviewer_ids)
    tiers: dict[str, list[str]] = {}
    for agent in agents.model_agents():
        if agent.id in reviewers and reviewer_mode != "model":
            continue
        tiers.setdefault(agent.model_tier, []).append(agent.id)
    return tiers


def check_model_keys(
    models: ModelCatalogue,
    agents: AgentCatalogue,
    keys: Mapping[str, str | None],
    reviewer_ids: Iterable[str],
    reviewer_mode: str,
) -> None:
    for tier, users in sorted(needed_tiers(agents, reviewer_ids, reviewer_mode).items()):
        if not any(keys.get(entry.provider) for entry in models.entries(tier)):
            raise MissingModelKey(
                f"profile {models.profile!r}, tier {tier!r} has no model with a configured key "
                f"(needed by {', '.join(sorted(users))}); set a provider key or use "
                "ADLC_REVIEWER_MODE=stub"
            )


class MissingKnowledgeToken(Exception):
    pass


def check_knowledge_token(
    agents: AgentCatalogue, token: str | None, knowledge_servers: Iterable[str] | None = None
) -> None:
    """008 research R-12: an agent with knowledge tools needs the knowledge server's token.
    010 T044: with the registry's knowledge servers given, only bindings to them count (tools on
    the tools and bridge hosts use run tokens instead)."""
    servers = None if knowledge_servers is None else set(knowledge_servers)

    def grounding(permission: str) -> bool:
        kind, _, rest = permission.partition(":")
        return kind == "mcp" and (servers is None or rest.partition(":")[0] in servers)

    grounded = sorted(
        a.id for a in agents.agents.values() if any(grounding(t.permission) for t in a.tools)
    )
    if grounded and not token:
        raise MissingKnowledgeToken(
            f"agents {', '.join(grounded)} have knowledge tools; set ADLC_KNOWLEDGE_TOKEN"
        )
