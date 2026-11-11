"""008 T031: the knowledge MCP server is its own process; it imports nothing from the platform's
orchestration, ledger, policy, agents or API code."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = sorted((ROOT / "src" / "adlc" / "knowledge").rglob("*.py"))
FORBIDDEN = (
    "adlc.orchestration",
    "adlc.ledger",
    "adlc.policy",
    "adlc.agents",
    "adlc.api",
    "adlc.inbox",
    "adlc.ui",
    "adlc.db",
    "sqlalchemy",
)


def imported(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("path", KNOWLEDGE, ids=lambda p: str(p.relative_to(ROOT)))
def test_knowledge_imports_no_platform_internals(path: Path) -> None:
    bad = sorted(n for n in imported(path) if n.startswith(FORBIDDEN))
    assert bad == []
