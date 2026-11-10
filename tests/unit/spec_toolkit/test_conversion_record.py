"""T042: CONVERSION.md accounts for every TDS element of every terminal (SC-003)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TDS = (ROOT / "docs" / "terminal-design-spec.md").read_text()
RECORD = ROOT / "adlc-specs" / "CONVERSION.md"


def _tds_block(n: int) -> str:
    """The YAML block of TDS section for terminal T<n>."""
    heading = re.search(rf"^## [0-9]+\. T{n} – .*$", TDS, re.MULTILINE)
    assert heading, f"T{n} section not found in TDS"
    rest = TDS[heading.end() :]
    block = re.search(r"```yaml\n(.*?)```", rest, re.DOTALL)
    assert block
    return block.group(1)


def _record_section(n: int) -> str:
    text = RECORD.read_text()
    match = re.search(rf"^## T{n}\b.*?(?=^## T[0-9]|\Z)", text, re.MULTILINE | re.DOTALL)
    assert match, f"CONVERSION.md has no section for T{n}"
    return match.group(0)


def _tds_elements(n: int) -> set[str]:
    block = _tds_block(n)
    ids = set(re.findall(r"\b(?:PRE|CTL|CHK)-T[0-9]+-[0-9]{2}\b|\bMON-[0-9]{2}\b", block))
    artifacts = set(re.findall(r"- \{id: ([a-z_]+), format:", block))
    trigger = re.search(r"\bon: \[([^\]]*)\]", block)
    events = {e.strip() for e in trigger.group(1).split(",")} if trigger else set()
    statuses = {
        s for s in ("pass", "rework", "exception", "escalate", "terminate") if f"    {s}:" in block
    }
    return ids | artifacts | events | statuses


@pytest.mark.parametrize("n", range(10))
def test_every_tds_element_is_recorded(n: int) -> None:
    section = _record_section(n)
    missing = sorted(e for e in _tds_elements(n) if f"`{e}`" not in section)
    assert missing == [], f"T{n}: not in CONVERSION.md: {missing}"
