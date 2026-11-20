"""The platform imports nothing from the ADO simulator (feature 015, SC-008, constitution VII)."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_platform_does_not_import_the_simulator() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / "src" / "adlc").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            offenders.extend(
                f"{path.relative_to(ROOT)}: {name}"
                for name in names
                if name.split(".")[0] == "ado_sim"
            )
    assert offenders == []
