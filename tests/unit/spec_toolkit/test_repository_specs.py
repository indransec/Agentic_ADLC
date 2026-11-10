"""T041: the repository's adlc-specs/ folder is valid and complete (US3, SC-004)."""

import re
from pathlib import Path

import pytest

from adlc.spec_toolkit.expressions import parse_expression
from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.rules import Context, validate
from adlc.spec_toolkit.rules.single_spec import expressions, spec

ROOT = Path(__file__).resolve().parents[3]
SPECS = ROOT / "adlc-specs"
TERMINALS = [f"T{n}" for n in range(10)]


@pytest.fixture(scope="module")
def bundle():  # type: ignore[no-untyped-def]
    return load_bundle(SPECS)


def test_no_errors(bundle) -> None:  # type: ignore[no-untyped-def]
    errors = [f for f in validate(Context(bundle)) if f.severity == "error"]
    assert errors == [], "\n".join(f"{f.location()} {f.rule_id} {f.message}" for f in errors)


def test_ten_terminals(bundle) -> None:  # type: ignore[no-untyped-def]
    assert sorted(bundle.terminals) == sorted(f"terminals/{t}.yaml" for t in TERMINALS)


def test_every_expression_parses(bundle) -> None:  # type: ignore[no-untyped-def]
    for loaded in bundle.terminals.values():
        for pointer, text in expressions(spec(loaded)):
            parse_expression(text)  # raises on free text (SC-004)
            assert not re.fullmatch(r"[a-z ]+", text.strip()), f"{loaded.rel}{pointer}: {text}"


def test_metadata(bundle) -> None:  # type: ignore[no-untyped-def]
    for loaded in bundle.terminals.values():
        meta = spec(loaded)["metadata"]
        assert meta["status"] == "active", loaded.rel
        assert meta["schema_version"] == "1.1.0", loaded.rel


def test_every_yaml_declares_its_schema() -> None:
    for path in sorted(SPECS.rglob("*.yaml")):
        first = path.read_text().splitlines()[0]
        assert first.startswith("# yaml-language-server: $schema="), path
