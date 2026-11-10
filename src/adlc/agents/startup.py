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
