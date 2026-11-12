"""T011 (FR-007): the tools each server declares are exactly those of contracts/tools-mcp.md, with
the same scopes, model arguments and bound values, so a real system's server can replace a mock."""

import re
from pathlib import Path

import pytest

from adlc.tools.catalogue import CATALOGUE, ENVIRONMENT_SCOPE, ToolSpec

CONTRACT = (
    Path(__file__).resolve().parents[3] / "specs" / "010-mcp-servers" / "contracts" / "tools-mcp.md"
)
TICKED = re.compile(r"`([a-z][a-z0-9_]*)`")


def contract_rows() -> dict[str, dict[str, set[str] | str]]:
    rows: dict[str, dict[str, set[str] | str]] = {}
    header: list[str] = []
    for line in CONTRACT.read_text().splitlines():
        if not line.startswith("|"):
            header = []
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0] == "Tool":
            header = cells
            continue
        if not header or set(cells[0]) <= {"-", " "}:
            continue
        row = dict(zip(header, cells, strict=False))
        name = TICKED.findall(row["Tool"])[0]
        scopes = TICKED.findall(row["Scope"])
        rows[name] = {
            "scope": ENVIRONMENT_SCOPE if scopes == ["dev", "test"] else scopes[0],
            "args": set(TICKED.findall(row.get("Model sets", ""))),
            "bound": set(TICKED.findall(row.get("Bound", ""))),
        }
    return rows


def test_every_contract_tool_is_declared_and_no_more() -> None:
    assert set(contract_rows()) == set(CATALOGUE.tools)


@pytest.mark.parametrize("name", sorted(CATALOGUE.tools))
def test_tool_matches_its_contract_row(name: str) -> None:
    row = contract_rows()[name]
    tool: ToolSpec = CATALOGUE.tools[name]
    assert tool.scope == row["scope"]
    assert set(tool.model_args()) == row["args"]
    assert set(tool.bound) | set(tool.bound_optional) == row["bound"]
