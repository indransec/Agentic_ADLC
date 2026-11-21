"""Loading and querying the tracker mapping; its check against a board (T017, FR-003, FR-004)."""

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

from adlc.engagement.mapping import MappingError, TrackerMapping
from adlc.engagement.model import BoardInfo, BoardType

ROOT = Path(__file__).resolve().parents[3]
MAPPING = ROOT / "adlc-specs" / "tracker_mapping.yaml"


@pytest.fixture
def mapping() -> TrackerMapping:
    return TrackerMapping.load(MAPPING)


def _raw() -> dict[str, Any]:
    data: dict[str, Any] = YAML(typ="safe").load(MAPPING.read_text())
    return data


def _board(mapping: TrackerMapping) -> BoardInfo:
    """A board offering exactly what the mapping names."""
    types = {}
    for kind in ("usecase", "run", "clarification"):
        item = mapping.item(kind)
        fields = set(item.fields.values())
        if kind == "run":
            fields |= mapping.person_input_fields("run")
        if kind == "clarification":
            fields |= mapping.person_input_fields("clarification")
        types[item.type] = BoardType(
            item.type, tuple(sorted(mapping.states_used(kind))), frozenset(fields)
        )
    return BoardInfo(types=types, areas=frozenset({mapping.area}))


def test_queries(mapping: TrackerMapping) -> None:
    raw = _raw()
    assert mapping.poll_interval == timedelta(seconds=10)
    assert mapping.area == raw["area"]
    first_terminal, first_column = next(iter(raw["items"]["usecase"]["columns"].items()))
    assert mapping.column(first_terminal) == first_column
    assert mapping.column("X99") is None
    assert mapping.item("run").type == raw["items"]["run"]["type"]
    assert mapping.field("usecase", "sub_stage") == raw["items"]["usecase"]["fields"]["sub_stage"]
    assert mapping.sub_stage("awaiting_sign_off") == raw["sub_stages"]["awaiting_sign_off"]
    assert mapping.run_item_state("closed") == raw["items"]["run"]["states"]["closed"]
    assert mapping.decision_field == raw["decision"]["field"]


def test_decision_values_both_ways(mapping: TrackerMapping) -> None:
    values = _raw()["decision"]["values"]
    for action, value in values.items():
        assert mapping.value_for(action) == value
        assert mapping.action_for(value) == action
        assert mapping.action_for(f"  {value.upper()} ") == action
    assert mapping.action_for("Maybe") is None
    assert mapping.allowed_values() == list(values.values())


def test_inputs_and_person_fields(mapping: TrackerMapping) -> None:
    raw = _raw()["decision"]
    inputs = mapping.inputs()
    assert {name: spec.field for name, spec in inputs.items()} == {
        name: spec["field"] for name, spec in raw["inputs"].items()
    }
    run_inputs = mapping.person_input_fields("run")
    assert raw["field"] in run_inputs and raw["comment"] in run_inputs
    assert all(spec["field"] in run_inputs for spec in raw["inputs"].values())
    answer = _raw()["items"]["clarification"]["fields"]["answer"]
    assert mapping.person_input_fields("clarification") == {answer}


def test_platform_written_refs(mapping: TrackerMapping) -> None:
    raw = _raw()
    expected = {raw["items"]["usecase"]["fields"][k] for k in raw["platform_written"]["usecase"]}
    assert mapping.platform_written("usecase") == expected


def test_names_lists_every_tracker_value(mapping: TrackerMapping) -> None:
    names = mapping.names()
    raw = _raw()
    assert raw["items"]["usecase"]["type"] in names
    assert raw["decision"]["values"]["pass"] in names
    assert raw["decision"]["inputs"]["reason"]["field"] in names
    assert raw["decision"]["inputs"]["reason"]["label"] not in names  # the platform's own word
    assert raw["area"] in names


def test_check_against_a_matching_board(mapping: TrackerMapping) -> None:
    assert mapping.check_against(_board(mapping)) == []


def test_check_names_every_gap(mapping: TrackerMapping) -> None:
    board = _board(mapping)
    run_type = mapping.item("run").type
    epic_type = mapping.item("usecase").type
    run = board.types[run_type]
    epic = board.types[epic_type]
    first_column = next(iter(_raw()["items"]["usecase"]["columns"].values()))
    broken = BoardInfo(
        types={
            epic_type: BoardType(
                epic_type, tuple(s for s in epic.states if s != first_column), epic.fields
            ),
            run_type: BoardType(run_type, run.states, run.fields - {mapping.decision_field}),
        },
        areas=frozenset(),
    )
    gaps = mapping.check_against(broken)
    text = "\n".join(gaps)
    assert mapping.item("clarification").type in text  # a type missing
    assert first_column in text  # a state missing
    assert mapping.decision_field in text  # a field missing
    assert mapping.area in text  # the area missing


def test_broken_file_names_file_and_path(tmp_path: Path) -> None:
    raw = _raw()
    del raw["decision"]["values"]["pass"]
    raw["inbound"]["mode"] = "webhooks"
    path = tmp_path / "tracker_mapping.yaml"
    YAML().dump(raw, path)
    with pytest.raises(MappingError) as raised:
        TrackerMapping.load(path, spec_root=ROOT / "adlc-specs")
    message = str(raised.value)
    assert str(path) in message and "/inbound/mode" in message


def test_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(MappingError, match="cannot read"):
        TrackerMapping.load(tmp_path / "missing.yaml")
