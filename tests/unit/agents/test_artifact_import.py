"""011 T005 (research R-08, contracts/artifact-import.md): a per-case table imported from a
recorded result; the agent's mapping sets req_id; anything else is an invalid output."""

from collections.abc import Mapping
from typing import Any

from adlc.agents.imports import CASE_COLUMNS, ImportSource, expand

CASES: list[Mapping[str, Any]] = [
    {
        "case_id": "INC-7-1",
        "expected": {"team": "a", "category": "network"},
        "actual": {"team": "a", "category": "network"},
        "score": 1.0,
        "result": "pass",
    },
    {
        "case_id": "INC-7-2",
        "expected": {"team": "b", "category": "access"},
        "actual": {"team": "c", "category": "access"},
        "score": 0.5,
        "result": "fail",
    },
]
SOURCE = ImportSource("RES-9", "harness", "sha256:" + "a" * 64, CASES)
MAPPING = {"field": "category", "map": {"network": "FR-03"}, "default": "FR-01"}


def resolve(result_id: str) -> ImportSource | None:
    return SOURCE if result_id == "RES-9" else None


def test_expansion_and_provenance() -> None:
    rows, provenance, problems = expand(
        "test_case_results",
        CASE_COLUMNS,
        {"import": {"result": "RES-9", "req_id_by": MAPPING}},
        resolve,
    )
    assert problems == []
    assert rows[0] == {
        "case_id": "INC-7-1",
        "req_id": "FR-03",
        "expected": "team=a; category=network",
        "actual": "team=a; category=network",
        "score": 1.0,
        "result": "pass",
    }
    assert rows[1]["req_id"] == "FR-01" and rows[1]["result"] == "fail"
    assert provenance is not None and (provenance.result_id, provenance.kind, provenance.rows) == (
        "RES-9",
        "harness",
        2,
    )


def test_invalid_imports() -> None:
    cases = [
        (
            {"import": {"result": "RES-404", "req_id_by": MAPPING}},
            CASE_COLUMNS,
            "not a case result of this run",
        ),
        ({"import": {"result": "RES-9"}}, CASE_COLUMNS, "req_id_by needs"),
        (
            {"import": {"result": "RES-9", "req_id_by": {"field": "category", "map": {}}}},
            CASE_COLUMNS,
            "no requirement for category=network",
        ),
        (
            {"import": {"result": "RES-9", "req_id_by": MAPPING}},
            ("metric", "actual"),
            "only a table with columns",
        ),
        ({"import": "RES-9"}, CASE_COLUMNS, "import must be an object"),
    ]
    for value, columns, fragment in cases:
        rows, provenance, problems = expand("t", columns, value, resolve)  # type: ignore[arg-type]
        assert rows == [] and provenance is None and fragment in problems[0], problems


def test_an_agent_cannot_write_a_signed_record() -> None:
    """011 FR-003: the attestation is people's sign-off; an agent that writes it is corrected."""
    import json

    from adlc.agents.output import parse_builder

    spec = {
        "terminal": {
            "evidence": {
                "artifacts": [
                    {
                        "id": "notes",
                        "format": "table",
                        "columns": ["a"],
                        "applicability": {"mode": "mandatory"},
                    },
                    {
                        "id": "assurance_attestation",
                        "format": "signed_record",
                        "columns": ["role", "decision", "date"],
                        "applicability": {"mode": "mandatory"},
                    },
                ]
            }
        }
    }
    written = json.dumps(
        {
            "artifacts": {
                "notes": [{"a": 1}],
                "assurance_attestation": [
                    {"role": "x", "decision": "approve", "date": "2026-01-01"}
                ],
            }
        }
    )
    parsed = parse_builder(written, spec, lambda a: True)
    assert any("signed by people" in p for p in parsed.problems)
    assert (
        parse_builder(
            json.dumps({"artifacts": {"notes": [{"a": 1}]}}), spec, lambda a: True
        ).problems
        == ()
    )
