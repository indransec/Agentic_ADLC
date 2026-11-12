"""T016: reproducible synthetic incidents with expected answers (FR-007 to FR-009, SC-005)."""

import json
from pathlib import Path

from pilot_tools.incidents import EDGE_CASES, generate, write
from tests.conftest import DEFAULT_FILL, TEMPLATE
from triage_agent.fill import load_fill
from triage_agent.pii import find_pii
from triage_agent.rai import jailbreak_count
from triage_agent.reference import Reference
from triage_agent.triage import Incident, SimulatedModel

CATEGORIES = {"access", "hardware", "software", "network", "security"}


def test_same_seed_same_set(tmp_path: Path) -> None:
    assert generate(seed=7, size=120) == generate(seed=7, size=120)
    assert generate(seed=7, size=120) != generate(seed=8, size=120)
    write(generate(seed=3, size=10), tmp_path / "a.jsonl")
    write(generate(seed=3, size=10), tmp_path / "b.jsonl")
    assert (tmp_path / "a.jsonl").read_bytes() == (tmp_path / "b.jsonl").read_bytes()


def test_coverage_labels_and_expected_answers() -> None:
    found = generate(seed=11, size=200)
    assert {i["edge_case"] for i in found} == set(EDGE_CASES)
    assert {i["expected"]["category"] for i in found} == CATEGORIES
    assert {i["expected"]["priority"] for i in found} == {"P1", "P2", "P3", "P4"}
    assert {i["urgency"] for i in found} == {"low", "medium", "high"}
    reference = Reference.load(TEMPLATE)
    for incident in found:
        assert incident["synthetic"] is True and incident["incident_id"].startswith("INC-11-")
        assert incident["expected"]["team"] in reference.teams
        assert {"name", "department", "persona"} <= set(incident["reporter"])
    assert all(not i["planted_pii"] for i in found)  # none unless requested
    assert not any(find_pii(i["description"]) for i in found)


def test_planted_data_only_where_requested() -> None:
    found = generate(seed=5, size=200, pii_share=0.2)
    planted = [i for i in found if i["planted_pii"]]
    assert 0.12 <= len(planted) / len(found) <= 0.28
    for incident in found:
        in_text = find_pii(incident["description"])
        assert sorted(in_text) == sorted(incident["planted_pii"])
        assert all(p.endswith("@example.com") or p.startswith("+44 7700 900") for p in in_text)


def test_the_default_fill_routes_at_least_90_percent() -> None:
    model = SimulatedModel(load_fill(TEMPLATE, DEFAULT_FILL), Reference.load(TEMPLATE))
    golden = generate(seed=2026, size=500)
    right = sum(
        model.triage(Incident.model_validate(i)).team == i["expected"]["team"] for i in golden
    )
    assert right / len(golden) >= 0.9


def test_jsonl_round_trip(tmp_path: Path) -> None:
    write(generate(seed=1, size=5), tmp_path / "x.jsonl")
    rows = [json.loads(line) for line in (tmp_path / "x.jsonl").read_text().splitlines()]
    assert [r["incident_id"] for r in rows] == [f"INC-1-{n}" for n in range(1, 6)]


def test_unsafe_text_is_counted_and_routed_to_first_line() -> None:
    """T032 (FR-007): unsafe wording is generated, counted as a jailbreak attempt, not obeyed."""
    model = SimulatedModel(load_fill(TEMPLATE, DEFAULT_FILL), Reference.load(TEMPLATE))
    unsafe = [i for i in generate(seed=11, size=400) if i["edge_case"] == "unsafe"]
    assert unsafe
    for incident in unsafe:
        assert jailbreak_count(incident["description"]) >= 1
        answer = model.triage(Incident.model_validate(incident))
        assert answer.team == incident["expected"]["team"] == Reference.load(TEMPLATE).first_line
