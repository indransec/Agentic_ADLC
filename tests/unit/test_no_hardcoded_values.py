"""Constitution I and II: no terminal, event or role values hard-coded in platform code (FR-028)."""

import re
from pathlib import Path

import pytest

from adlc.identity.catalogue import load_role_ids

ROOT = Path(__file__).resolve().parents[2]
SOURCES = sorted((ROOT / "src" / "adlc").rglob("*.py"))
TERMINAL_ID = re.compile(r"\bT[0-9]\b")
EVENT_NAME = re.compile(r"\bT[0-9]\.[a-z]")


def _code_lines(path: Path) -> list[tuple[int, str]]:
    return list(enumerate(path.read_text().splitlines(), start=1))


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_terminal_ids_or_events(path: Path) -> None:
    hits = [
        f"{path.name}:{number}: {line.strip()}"
        for number, line in _code_lines(path)
        if TERMINAL_ID.search(line) or EVENT_NAME.search(line)
    ]
    assert hits == []


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_role_ids(path: Path) -> None:
    roles = load_role_ids(ROOT / "adlc-specs" / "shared" / "roles.yaml")
    pattern = re.compile(r"\b(" + "|".join(sorted(roles)) + r")\b")
    hits = [
        f"{path.name}:{number}: {line.strip()}"
        for number, line in _code_lines(path)
        if pattern.search(line)
    ]
    assert hits == []
