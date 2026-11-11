"""007 T031, FR-020: the web application reaches the platform only through the API.

Modules in ``src/adlc/ui/`` import only ``adlc.ui`` and ``adlc.config`` from the platform, and
never a database driver or the services.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
UI = sorted((ROOT / "src" / "adlc" / "ui").rglob("*.py"))
ALLOWED_PLATFORM = ("adlc.ui", "adlc.config")
FORBIDDEN = ("sqlalchemy", "psycopg", "psycopg2", "asyncpg", "alembic")


def imported(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
        elif isinstance(node, ast.ImportFrom) and node.level:
            raise AssertionError(f"{path.name}: relative imports hide the boundary")
    return names


def allowed(name: str) -> bool:
    if name.split(".")[0] in FORBIDDEN:
        return False
    if name == "adlc" or name.startswith("adlc."):
        return any(name == a or name.startswith(a + ".") for a in ALLOWED_PLATFORM)
    return True


@pytest.mark.parametrize("path", UI, ids=lambda p: str(p.relative_to(ROOT)))
def test_ui_imports_only_the_api_client_and_settings(path: Path) -> None:
    assert sorted(n for n in imported(path) if not allowed(n)) == []


def test_the_scan_sees_every_page() -> None:
    assert {p.name for p in UI} >= {"app.py", "client.py", "render.py", "run.py", "inbox.py"}
    assert not allowed("adlc.orchestration.service") and not allowed("sqlalchemy.engine")
    assert not allowed("adlc.inbox.rules") and allowed("adlc.config.settings")
