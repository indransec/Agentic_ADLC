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
    assert [p.data["id"] for p in bundle.prompts.values()] == ["common-terminal-reviewer"]


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


def test_every_terminal_agent_is_a_stub_until_008_and_the_reviewer_is_a_model() -> None:
    agents = load_bundle(SPECS).catalogue_data("agents")["agents"]
    implementations = {a["id"]: a["implementation"] for a in agents}
    assert implementations.pop("common-terminal-reviewer") == "model"
    assert set(implementations.values()) == {"stub"} and len(implementations) == 10
