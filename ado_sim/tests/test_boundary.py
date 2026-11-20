"""The simulator shares nothing with the platform (FR-023, SC-008, constitution VII)."""

import ast
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SOURCES = sorted((PROJECT / "src").rglob("*.py")) + sorted((PROJECT / "tests").rglob("*.py"))


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def test_sources_exist() -> None:
    assert any(path.name == "app.py" for path in SOURCES) or SOURCES


def test_no_module_imports_the_platform() -> None:
    offenders = {
        str(path.relative_to(PROJECT)): sorted(
            name for name in _imported_modules(path) if name.split(".")[0] == "adlc"
        )
        for path in SOURCES
    }
    assert {path: names for path, names in offenders.items() if names} == {}


def test_no_platform_settings_are_read() -> None:
    marker = "ADLC" + "_"
    files = [*sorted((PROJECT / "src").rglob("*")), *sorted((PROJECT / "seed").rglob("*"))]
    offenders = [
        str(path.relative_to(PROJECT))
        for path in files
        if path.is_file()
        and path.suffix in {".py", ".sql", ".yaml"}
        and marker in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
