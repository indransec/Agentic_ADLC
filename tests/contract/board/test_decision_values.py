"""018 T003: the decision values the simulator's form offers equal the tracker mapping's.

Both are data files read as YAML; the platform imports nothing from the simulator. The mapping
leads: change it first, then the simulator's seed.
"""

from __future__ import annotations

from typing import Any

from ruamel.yaml import YAML

from tests.contract.board.conftest import ROOT


def _decision_allowed(seed: dict[str, Any], field: str) -> list[str]:
    for kind in seed["process"]["types"].values():
        for entry in kind.get("fields") or []:
            if isinstance(entry, dict) and entry.get("ref") == field:
                return [str(v) for v in entry["allowed_values"]]
    raise AssertionError(f"the simulator seed gives {field} no allowed values")


def test_the_form_offers_the_mapping_s_decision_values() -> None:
    mapping = YAML(typ="safe").load((ROOT / "adlc-specs" / "tracker_mapping.yaml").read_text())
    seed = YAML(typ="safe").load((ROOT / "ado_sim" / "seed" / "demo.yaml").read_text())
    field = mapping["decision"]["field"]
    assert _decision_allowed(seed, field) == [
        str(v) for v in mapping["decision"]["values"].values()
    ]
