"""010 T005: the tool servers are their own processes. They import nothing from the platform's
orchestration, ledger, policy, agents, API, inbox or UI code; the bridge (the only service on both
networks) does not touch the database either (research R-01)."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "src" / "adlc" / "tools"
SERVER_CODE = sorted(p for p in TOOLS.rglob("*.py") if p.name != "probe.py")
BRIDGE_CODE = sorted((TOOLS / "bridge").rglob("*.py"))
FORBIDDEN = (
    "adlc.orchestration",
    "adlc.ledger",
    "adlc.policy",
    "adlc.agents",
    "adlc.api",
    "adlc.inbox",
    "adlc.ui",
    "adlc.knowledge",
)
BRIDGE_FORBIDDEN = ("sqlalchemy", "psycopg", "adlc.db", "adlc.tools.enterprise", "litellm")


def imported(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("path", SERVER_CODE, ids=lambda p: str(p.relative_to(ROOT)))
def test_servers_import_no_platform_internals(path: Path) -> None:
    assert sorted(n for n in imported(path) if n.startswith(FORBIDDEN)) == []


@pytest.mark.parametrize("path", BRIDGE_CODE, ids=lambda p: str(p.relative_to(ROOT)))
def test_bridge_touches_no_database_or_model(path: Path) -> None:
    assert sorted(n for n in imported(path) if n.startswith(BRIDGE_FORBIDDEN)) == []
