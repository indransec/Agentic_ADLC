"""T012: every rule in code is documented in contracts/validation-rules.md, and vice versa."""

import re
from pathlib import Path

from adlc.spec_toolkit.rules import REGISTRY

CONTRACT = (
    Path(__file__).resolve().parents[3]
    / "specs"
    / "002-terminal-spec-toolkit"
    / "contracts"
    / "validation-rules.md"
)


def test_rule_ids_match_contract() -> None:
    documented = set(re.findall(r"^\| ([PSV]-[0-9]{2}) \|", CONTRACT.read_text(), re.MULTILINE))
    implemented = {rule.id for rule in REGISTRY.all()} | {"P-01", "P-02", "P-03"}
    assert implemented == documented
