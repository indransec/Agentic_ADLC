"""The ADO adapter reads every 015 success fixture it relies on (T014, FR-025).

The fixtures are the simulator's published contract (``ado_sim/contract/fixtures/``). Their
bodies hold type placeholders (``<int>``, ``<url>`` …, see the fixtures' README); they are filled
with sample values, then decoded with the adapter's readers. A change to the simulator's answers
that the adapter cannot read fails here, in the platform's build.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from adlc.engagement import ado

FIXTURES = Path(__file__).resolve().parents[3] / "ado_sim" / "contract" / "fixtures"
SAMPLES = {
    "<int>": 7,
    "<string>": "text",
    "<datetime>": "2026-11-21T10:00:00.000001Z",
    "<uuid>": "00000000-0000-0000-0000-000000000001",
    "<url>": "http://board.test/adlc-demo/_apis/wit/workItems/7",
    "<any>": None,
}


def _filled(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _filled(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_filled(v) for v in value if v != "<more>"]
    if isinstance(value, str) and value in SAMPLES:
        return SAMPLES[value]
    return value


def _body(name: str) -> Any:
    fixture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    assert fixture["expected"]["status"] == 200, name
    return _filled(fixture["expected"]["body"])


@pytest.mark.parametrize(
    "name",
    [
        "create/epic",
        "create/task_with_parent",
        "get/item",
        "update/fields_and_rev_test",
        "update/add_link",
        "revisions/get",
    ],
)
def test_items_decode(name: str) -> None:
    item = ado._item(_body(name))
    assert item.id == 7 and item.rev >= 1 and item.type
    assert item.changed_by is not None and "@" in item.changed_by


def test_parent_link_is_read() -> None:
    assert ado._item(_body("create/task_with_parent")).parent_id == 7


@pytest.mark.parametrize("name", ["updates/list"])
def test_updates_decode(name: str) -> None:
    updates = [ado._update(u) for u in _body(name)["value"]]
    assert updates and all(u.changed_by for u in updates)
    assert any(u.is_revision for u in updates)


def test_single_update_decodes() -> None:
    update = ado._update(_body("updates/get"))
    assert update.fields and update.rev == 2


def test_query_answer_has_ids_and_as_of() -> None:
    body = _body("wiql/flat")
    assert [int(w["id"]) for w in body["workItems"]]
    assert isinstance(body["asOf"], str)


def test_identity_answer_has_account_and_name() -> None:
    entry = _body("identities/search")["value"][0]
    assert entry["properties"]["Account"]["$value"]
    assert entry["providerDisplayName"] and entry["id"]


def test_types_and_areas_decode() -> None:
    kinds = _body("work_item_types/list")["value"]
    assert all(k["name"] and k["states"] and k["fields"] for k in kinds)
    assert all(f["referenceName"] for k in kinds for f in k["fields"])
    areas = ado._area_paths(_body("areas/get"))
    assert areas[0] and any("\\" in a for a in areas)
