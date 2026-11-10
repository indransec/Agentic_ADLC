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


CATALOGUE_FIELD = "# catalogue-field"


def _catalogue_field(line: str, path: Path) -> bool:
    """An evidence-source field name that equals a role id (evidence_sources.yaml), marked on the
    line and only in the evidence provider. It names data, not a role check."""
    return line.rstrip().endswith(CATALOGUE_FIELD) and path.name == "evidence.py"


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_role_ids(path: Path) -> None:
    roles = load_role_ids(ROOT / "adlc-specs" / "shared" / "roles.yaml")
    pattern = re.compile(r"\b(" + "|".join(sorted(roles)) + r")\b")
    hits = [
        f"{path.name}:{number}: {line.strip()}"
        for number, line in _code_lines(path)
        if pattern.search(line) and not _catalogue_field(line, path)
    ]
    assert hits == []


ORCHESTRATION = sorted(
    [
        *(ROOT / "src" / "adlc" / "orchestration").rglob("*.py"),
        *(ROOT / "src" / "adlc" / "policy").rglob("*.py"),
        *(ROOT / "src" / "adlc" / "ledger").rglob("*.py"),
    ]
)


def _destination_ids() -> set[str]:
    from ruamel.yaml import YAML

    data = YAML(typ="safe").load(
        (ROOT / "adlc-specs" / "shared" / "route_destinations.yaml").read_text()
    )
    items = data["route_destinations"]
    kinds = {str(i["kind"]) for i in items}
    # A destination is handled by its kind (FR-016); an id that is also a kind name is the kind.
    return {str(i["id"]) for i in items} - kinds


@pytest.mark.parametrize("path", ORCHESTRATION, ids=lambda p: str(p.relative_to(ROOT)))
def test_orchestration_names_no_route_destination(path: Path) -> None:
    """003 T072, 004 T050, 005 T033: destinations are handled by kind, never by name
    (constitution I)."""
    pattern = re.compile(r"\b(" + "|".join(sorted(_destination_ids())) + r")\b")
    hits = [
        f"{path.name}:{number}: {line.strip()}"
        for number, line in _code_lines(path)
        if pattern.search(line)
    ]
    assert hits == []
