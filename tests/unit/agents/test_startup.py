"""T019: model agents or the model reviewer need a keyed model for their tier (FR-018)."""

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
    models, agents = load_catalogues(registry, "dev")
    check_model_keys(models, agents, NO_KEYS, [REVIEWER], "stub")  # terminal agents are stubs


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
