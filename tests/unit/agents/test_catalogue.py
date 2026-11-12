"""T013: model catalogue profiles, data-class ranks, limits and agent definitions (006)."""

from decimal import Decimal
from pathlib import Path

import pytest

from adlc.agents.catalogue import (
    AgentCatalogue,
    ModelCatalogue,
    UnknownAgent,
    UnknownProfile,
    estimate_tokens,
    load_catalogues,
)
from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.registry import InMemorySpecRegistry

SPECS = Path(__file__).resolve().parents[3] / "adlc-specs"


@pytest.fixture(scope="module")
def registry() -> InMemorySpecRegistry:
    return InMemorySpecRegistry.from_bundle(load_bundle(SPECS))


def test_profile_selection(registry: InMemorySpecRegistry) -> None:
    models, _ = load_catalogues(registry, "default")
    assert [e.model for e in models.entries("standard")][0] == "anthropic/claude-sonnet-5-5"
    dev, _ = load_catalogues(registry, "dev")
    assert [e.model for e in dev.entries("reasoning")][:2] == [
        "openai/gpt-4o-mini",
        "gemini/gemini-2.5-flash",
    ]
    with pytest.raises(UnknownProfile, match="nightly"):
        load_catalogues(registry, "nightly")
    with pytest.raises(KeyError):
        models.entries("quantum")


def test_entry_fields_and_cost(registry: InMemorySpecRegistry) -> None:
    dev, _ = load_catalogues(registry, "dev")
    mini = dev.entries("reasoning")[0]
    assert (mini.provider, mini.max_output_tokens, mini.context_tokens) == ("openai", 16384, 128000)
    assert mini.cost(1_000_000, 1_000_000) == Decimal("0.750000")  # 0.15 + 0.60
    assert mini.cost(1000, 200) == Decimal("0.000270")
    unknown = ModelCatalogue.from_content(
        {
            "profiles": {
                "default": {
                    "reasoning": [
                        {
                            "provider": "openai",
                            "model": "openai/x",
                            "input_per_mtok": None,
                            "output_per_mtok": 1.0,
                            "max_output_tokens": 10,
                            "context_tokens": 100,
                            "max_data_class": "internal",
                        }
                    ]
                }
            }
        },
        "default",
        {"internal": 2},
    )
    assert unknown.entries("reasoning")[0].cost(10, 10) is None


def test_data_class_rank(registry: InMemorySpecRegistry) -> None:
    models, _ = load_catalogues(registry, "default")
    entry = models.entries("reasoning")[0]  # approved up to confidential_masked
    assert models.allows(entry, "internal")
    assert models.allows(entry, "confidential_masked")
    assert not models.allows(entry, "confidential")
    assert not models.allows(entry, "restricted")
    # A resolver or unknown ceiling counts as the highest rank: fails closed.
    assert not models.allows(entry, "per_T2_prod_design")
    assert not models.allows(entry, "no_such_class")


def test_context_window_and_output_cap(registry: InMemorySpecRegistry) -> None:
    dev, _ = load_catalogues(registry, "dev")
    mini = dev.entries("reasoning")[0]
    assert mini.fits(estimate_tokens("x" * 400_000))  # 100k tokens < 128k
    assert not mini.fits(estimate_tokens("x" * 600_000))
    assert mini.capped(50_000) == 16384 and mini.capped(1000) == 1000
    assert estimate_tokens("abcd" * 10) == 10


def test_agents(registry: InMemorySpecRegistry) -> None:
    _, agents = load_catalogues(registry, "default")
    reviewer = agents.agent("common-terminal-reviewer")
    assert (reviewer.implementation, reviewer.model_tier) == ("model", "reasoning")
    assert reviewer.prompt == ("common-terminal-reviewer", "1.0.0")
    assert agents.agent("t3-builder-agent").model_tier == "coding"
    assert agents.agent("t3-builder-agent").prompt == ("t3-builder-agent", "1.0.0")  # 011
    with pytest.raises(UnknownAgent):
        agents.agent("t42-agent")
    tooled = AgentCatalogue.from_content(
        {
            "agents": [
                {
                    "id": "a",
                    "version": "1.0.0",
                    "implementation": "model",
                    "model_tier": "reasoning",
                    "prompt": {"id": "a", "version": "1.0.0"},
                    "tools": [
                        {"tool": "kb", "permission": "read:knowledge_base"},
                        {"tool": "jira", "permission": "mcp:jira:read"},
                    ],
                }
            ]
        }
    )
    kb, jira = tooled.agent("a").tools
    assert (kb.action, kb.resource) == ("read", "knowledge_base")
    assert (jira.action, jira.resource) == ("mcp", "jira:read")
    assert tooled.agent("a").tool("jira") is jira and tooled.agent("a").tool("nope") is None
