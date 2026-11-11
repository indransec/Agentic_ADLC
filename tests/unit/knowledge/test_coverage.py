"""T017: every grounding scope item of a grounded terminal has at least one document in the demo
knowledge set (FR-012), and every document is labelled synthetic."""

from pathlib import Path

import pytest
from ruamel.yaml import YAML

from adlc.knowledge.documents import load_folder
from adlc.knowledge.scope import Scope
from adlc.spec_toolkit.loader import load_bundle

ROOT = Path(__file__).resolve().parents[3]
SPECS = ROOT / "adlc-specs"
KNOWLEDGE = ROOT / "data" / "knowledge"


def ranks() -> dict[str, int]:
    data = YAML(typ="safe").load((SPECS / "shared" / "data_classes.yaml").read_text())
    return {str(d["id"]): int(d["rank"]) for d in data["data_classes"]}


def grounded_items() -> list[tuple[str, str, str]]:
    bundle = load_bundle(SPECS)
    agents = {a["id"]: a for a in bundle.catalogue_data("agents")["agents"]}
    found = []
    for loaded in bundle.terminals.values():
        terminal = loaded.data["terminal"]
        agent = agents[terminal["actors"]["agent"]["id"]]
        bound = {t["permission"].split(":")[1] for t in agent.get("tools") or []}
        for entry in terminal["playbooks"].get("grounding") or []:
            if entry["mcp"] in bound:
                for item in str(entry["scope"]).split(","):
                    found.append((terminal["metadata"]["id"], entry["mcp"], item.strip()))
    return found


ITEMS = grounded_items()


def test_there_are_grounded_terminals() -> None:
    assert {t for t, _, _ in ITEMS} >= {"T0", "T1", "T2"}


@pytest.mark.parametrize(("terminal", "source", "item"), ITEMS, ids=lambda v: str(v))
def test_every_scope_item_has_a_document(terminal: str, source: str, item: str) -> None:
    documents = [d for d in load_folder(KNOWLEDGE, ranks()) if d.source == source]
    scope = Scope.parse([item])
    assert any(scope.contains(d) for d in documents), (terminal, source, item)


def test_demo_documents_are_synthetic_and_classified() -> None:
    files = [p for p in KNOWLEDGE.glob("*/**/*.md")]
    loaded = load_folder(KNOWLEDGE, ranks())
    assert len(loaded) == len(files) and all(d.synthetic for d in loaded)
