"""T007: the real model and agent catalogues and prompts load and agree (feature 006).

The rules themselves are covered by the negative fixtures V-27..V-30, S-02 and S-03."""

from pathlib import Path

from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.rules import Context, validate

SPECS = Path(__file__).resolve().parents[3] / "adlc-specs"


def test_repository_catalogues_have_no_errors() -> None:
    bundle = load_bundle(SPECS)
    errors = [f for f in validate(Context(bundle)) if f.severity == "error"]
    assert errors == []
    assert sorted(p.data["id"] for p in bundle.prompts.values()) == [
        "common-terminal-reviewer",
        "t0-intake-agent",
        "t1-requirements-agent",
        "t2-architect-agent",
    ]


def test_profiles_order_and_data_class() -> None:
    profiles = load_bundle(SPECS).catalogue_data("model_catalogue")["profiles"]
    assert set(profiles) == {"default", "dev"}
    for tier in ("reasoning", "coding", "standard"):
        default = [e["provider"] for e in profiles["default"][tier]]
        assert default == ["anthropic", "openai", "gemini"]  # ADR-02 production order
        dev = [e["model"] for e in profiles["dev"][tier]]
        assert dev[:2] == ["openai/gpt-4o-mini", "gemini/gemini-2.5-flash"]
        assert dev[2:] == [e["model"] for e in profiles["default"][tier]]
        assert {e["max_data_class"] for p in profiles.values() for e in p[tier]} == {
            "confidential_masked"
        }


def test_t0_to_t2_are_grounded_models_and_the_rest_stubs() -> None:
    """008: T0-T2 agents are model agents with a prompt and knowledge tools for exactly the
    sources in both their terminal's tool scopes and grounding (FR-002); T3-T9 stay stubs."""
    bundle = load_bundle(SPECS)
    agents = {a["id"]: a for a in bundle.catalogue_data("agents")["agents"]}
    assert agents.pop("common-terminal-reviewer")["implementation"] == "model"
    terminals = {
        t.data["terminal"]["actors"]["agent"]["id"]: t.data["terminal"]
        for t in bundle.terminals.values()
    }
    models = {aid for aid, a in agents.items() if a["implementation"] == "model"}
    assert len(models) == 3 and len(agents) == 10
    for aid in models:
        terminal = terminals[aid]
        scoped = {s.split(":")[1] for s in terminal["authorities"]["tool_scopes"]}
        grounded = {g["mcp"] for g in terminal["playbooks"]["grounding"]}
        bound = {t["permission"].split(":")[1] for t in agents[aid]["tools"]}
        assert bound == scoped & grounded, aid
        assert agents[aid]["prompt"]["id"] == aid
    assert all(not a["tools"] for aid, a in agents.items() if aid not in models)
