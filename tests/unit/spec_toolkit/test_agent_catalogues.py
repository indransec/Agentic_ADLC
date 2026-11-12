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
    agents = bundle.catalogue_data("agents")["agents"]
    prompted = sorted(a["prompt"]["id"] for a in agents if a.get("prompt"))
    assert sorted(p.data["id"] for p in bundle.prompts.values()) == prompted


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


def test_model_agents_tools_follow_their_terminals() -> None:
    """008: grounded agents get knowledge tools for exactly the sources in both their terminal's
    tool scopes and grounding (FR-002). 011: acting agents' tool permissions are within their
    terminal's tool scopes. Stub agents have no tools."""
    bundle = load_bundle(SPECS)
    agents = {a["id"]: a for a in bundle.catalogue_data("agents")["agents"]}
    assert agents.pop("common-terminal-reviewer")["implementation"] == "model"
    terminals = {
        t.data["terminal"]["actors"]["agent"]["id"]: t.data["terminal"]
        for t in bundle.terminals.values()
    }
    knowledge = {
        s["id"]
        for s in bundle.catalogue_data("mcp_servers")["mcp_servers"]
        if s["host"] == "knowledge"
    }
    models = {aid for aid, a in agents.items() if a["implementation"] == "model"}
    assert {"t0-intake-agent", "t1-requirements-agent", "t2-architect-agent"} <= models
    assert len(agents) == 10
    for aid in models:
        terminal = terminals[aid]
        scopes = set(terminal["authorities"]["tool_scopes"])
        scoped = {s.split(":")[1] for s in scopes}
        grounded = {g["mcp"] for g in terminal["playbooks"]["grounding"]}
        permissions = {t["permission"] for t in agents[aid]["tools"]}
        bound = {p.split(":")[1] for p in permissions}
        assert bound & knowledge == scoped & grounded & knowledge, aid
        assert {p for p in permissions if p.split(":")[1] not in knowledge} <= scopes, aid
        assert agents[aid]["prompt"]["id"] == aid
    assert all(not a["tools"] for aid, a in agents.items() if aid not in models)
