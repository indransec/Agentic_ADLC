"""018 T005: the seed's form layout (FR-002; research R-04)."""

from __future__ import annotations

from typing import Any

import pytest
from ruamel.yaml import YAML

from ado_sim.db import Database
from ado_sim.process import form_layout
from ado_sim.seed import SeedError, parse_seed
from tests.conftest import SEED


def _raw() -> dict[str, Any]:
    data: dict[str, Any] = YAML(typ="safe").load(SEED.read_text())
    return data


def test_the_demo_layout() -> None:
    layout = parse_seed(_raw()).form
    assert [s.title for s in layout["Feature"]] == ["Decision", "Run"]
    assert layout["Feature"][0].fields[0] == "Custom.AdlcDecision"


def test_no_form_section_is_valid() -> None:
    raw = _raw()
    del raw["form"]
    assert parse_seed(raw).form == {}


@pytest.mark.parametrize(
    ("layout", "named"),
    [
        ({"Saga": [{"title": "x", "fields": ["System.Title"]}]}, "form.Saga"),
        ({"Epic": [{"title": "x", "fields": ["Custom.Missing"]}]}, "Custom.Missing"),
        ({"Epic": [{"title": "x", "fields": ["System.Title", "System.Title"]}]}, "twice"),
        ({"Epic": [{"title": "", "fields": ["System.Title"]}]}, "title"),
        ({"Epic": [{"title": "x", "fields": ["System.Title"], "extra": 1}]}, "unknown key"),
    ],
)
def test_refusals_name_the_key(layout: dict[str, Any], named: str) -> None:
    raw = _raw()
    raw["form"] = layout
    with pytest.raises(SeedError, match=named):
        parse_seed(raw)


def test_loaded_layout(db: Database) -> None:
    with db.read() as conn:
        layout = form_layout(conn)
    assert [s.title for s in layout["Task"]] == ["Clarification", "Details"]
    assert layout["Task"][1].fields == ("System.Title", "System.State", "Custom.AdlcRunId")
