"""T019: model agents or the model reviewer need a keyed model for their tier (FR-018)."""

from dataclasses import replace
from pathlib import Path

import pytest

from adlc.agents.catalogue import AgentCatalogue, load_catalogues
from adlc.agents.startup import MissingModelKey, check_model_keys
from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.registry import InMemorySpecRegistry

SPECS = Path(__file__).resolve().parents[3] / "adlc-specs"
REVIEWER = "common-terminal-reviewer"
NO_KEYS = {"anthropic": None, "openai": None, "gemini": None}


@pytest.fixture(scope="module")
def registry() -> InMemorySpecRegistry:
    return InMemorySpecRegistry.from_bundle(load_bundle(SPECS))


def test_stub_mode_needs_no_keys(registry: InMemorySpecRegistry) -> None:
    """With stub builders and the stub reviewer, no key is needed (006)."""
    models, agents = load_catalogues(registry, "dev")
    stubs = AgentCatalogue(
        {aid: replace(a, implementation="stub") for aid, a in agents.agents.items()}
    )
    check_model_keys(models, stubs, NO_KEYS, [REVIEWER], "stub")


def test_model_builders_need_a_key(registry: InMemorySpecRegistry) -> None:
    """008: the registered T0-T2 agents are model agents, so even stub-reviewer mode needs a key."""
    models, agents = load_catalogues(registry, "dev")
    with pytest.raises(MissingModelKey, match="t0-intake-agent"):
        check_model_keys(models, agents, NO_KEYS, [REVIEWER], "stub")


def test_model_reviewer_needs_a_key(registry: InMemorySpecRegistry) -> None:
    models, agents = load_catalogues(registry, "dev")
    with pytest.raises(MissingModelKey, match="profile 'dev', tier 'reasoning'"):
        check_model_keys(models, agents, NO_KEYS, [REVIEWER], "model")
    check_model_keys(models, agents, {**NO_KEYS, "openai": "k"}, [REVIEWER], "model")
    default, _ = load_catalogues(registry, "default")
    check_model_keys(default, agents, {**NO_KEYS, "gemini": "k"}, [REVIEWER], "model")


def test_model_terminal_agent_needs_its_tier(registry: InMemorySpecRegistry) -> None:
    models, _ = load_catalogues(registry, "default")
    builder = AgentCatalogue.from_content(
        {
            "agents": [
                {
                    "id": "b",
                    "version": "1.0.0",
                    "implementation": "model",
                    "model_tier": "coding",
                    "prompt": {"id": "b", "version": "1.0.0"},
                    "tools": [],
                }
            ]
        }
    )
    with pytest.raises(MissingModelKey, match="tier 'coding'.*needed by b"):
        check_model_keys(models, builder, NO_KEYS, [], "stub")


def test_knowledge_tools_need_a_token() -> None:
    """008 T007a: refuse to start when an agent has knowledge tools and no token is set."""
    from adlc.agents.catalogue import AgentCatalogue, AgentDefinition, ToolBinding
    from adlc.agents.startup import MissingKnowledgeToken, check_knowledge_token

    grounded = AgentDefinition(
        "a", "1", "model", "reasoning", ("a", "1"), (ToolBinding("x_search", "mcp:x:read"),)
    )
    plain = AgentDefinition("b", "1", "stub", "reasoning", None)
    with pytest.raises(MissingKnowledgeToken):
        check_knowledge_token(AgentCatalogue({"a": grounded}), None)
    check_knowledge_token(AgentCatalogue({"a": grounded}), "k" * 16)
    check_knowledge_token(AgentCatalogue({"b": plain}), None)


def test_tools_on_the_tool_hosts_do_not_need_the_knowledge_token() -> None:
    """010 T044: only bindings to knowledge-host servers need the knowledge token."""
    from adlc.agents.catalogue import AgentCatalogue, AgentDefinition, ToolBinding
    from adlc.agents.startup import MissingKnowledgeToken, check_knowledge_token

    acting = AgentDefinition(
        "t3", "1.0.0", "model", "coding", None, (ToolBinding("ci_run", "mcp:ci:run"),)
    )
    check_knowledge_token(AgentCatalogue({"a": acting}), None, ["confluence", "jira"])
    grounded = AgentDefinition(
        "t1", "1.0.0", "model", "reasoning", None, (ToolBinding("jira_search", "mcp:jira:read"),)
    )
    with pytest.raises(MissingKnowledgeToken):
        check_knowledge_token(AgentCatalogue({"a": grounded}), None, ["confluence", "jira"])
