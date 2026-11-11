"""T005: fill validation names the failing part (FR-002)."""

import shutil
from pathlib import Path

import pytest

from tests.conftest import DEFAULT_FILL, TEMPLATE
from triage_agent.fill import FillError, load_fill


def copy(tmp_path: Path) -> Path:
    target = tmp_path / "fill"
    shutil.copytree(DEFAULT_FILL, target)
    return target


def test_the_default_fill_is_valid() -> None:
    fill = load_fill(TEMPLATE, DEFAULT_FILL)
    assert fill.settings.model_mode == "simulated" and fill.settings.token_budget == 1500
    assert fill.routing.category_teams["security"] == "security-ops"
    assert fill.tools == frozenset({"service_catalogue", "team_directory"})


@pytest.mark.parametrize(
    ("file", "old", "new", "part"),
    [
        ("instructions.md", None, "", "instructions"),
        ("instructions.md", None, "x" * 20_001, "instructions"),
        ("routing_rules.yaml", "network: network-ops", "network: no-such-team", "routing_rules"),
        ("routing_rules.yaml", "  network: [vpn", "  telepathy: [vpn", "routing_rules"),
        ("tool_bindings.yaml", "team_directory]", "team_directory, payroll_api]", "tool_bindings"),
        ("thresholds.yaml", "0.5", "1.5", "thresholds"),
        ("thresholds.yaml", "true", "maybe", "thresholds"),
        ("settings.yaml", "1500", "50", "settings"),
        ("settings.yaml", "1500", "9000", "settings"),
        ("settings.yaml", "simulated", "telepathic", "settings"),
    ],
)
def test_each_rule_names_the_part(
    tmp_path: Path, file: str, old: str | None, new: str, part: str
) -> None:
    fill = copy(tmp_path)
    path = fill / file
    path.write_text(new if old is None else path.read_text().replace(old, new))
    with pytest.raises(FillError) as raised:
        load_fill(TEMPLATE, fill)
    assert raised.value.part == part and str(raised.value)


def test_a_missing_file_names_the_part(tmp_path: Path) -> None:
    fill = copy(tmp_path)
    (fill / "settings.yaml").unlink()
    with pytest.raises(FillError) as raised:
        load_fill(TEMPLATE, fill)
    assert raised.value.part == "settings"
