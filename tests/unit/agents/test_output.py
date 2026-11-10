"""T021: builder and reviewer output validation, without echoing content (FR-013, FR-017)."""

from pathlib import Path
from typing import Any

import pytest

from adlc.agents.output import correction, parse_builder, parse_json, parse_review
from adlc.orchestration import spec_view
from adlc.orchestration.interfaces import Artifacts, Clarification, Recommendation
from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.registry import InMemorySpecRegistry

SPECS = Path(__file__).resolve().parents[3] / "adlc-specs"
ITEMS = ["CHK-T1-01", "CHK-T1-02"]
CAUSES = {"requirement", "design"}


@pytest.fixture(scope="module")
def spec() -> Any:
    entry = InMemorySpecRegistry.from_bundle(load_bundle(SPECS)).entry("T1")
    assert entry is not None
    return entry.spec


def _valid(spec: Any) -> dict[str, Any]:
    return {a.id: [{c: f"{c}-1" for c in a.columns}] for a in spec_view.artifacts(spec)}


def always(_: Any) -> bool:
    return True


def test_parse_json_fenced_and_bare() -> None:
    assert parse_json('Here:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('text {"a": {"b": 2}} more') == {"a": {"b": 2}}
    assert parse_json("no json") is None and parse_json("[1, 2]") is None


def test_valid_artifacts(spec: Any) -> None:
    import json

    parsed = parse_builder(json.dumps({"artifacts": _valid(spec)}), spec, always)
    assert isinstance(parsed.result, Artifacts) and parsed.problems == ()


def test_artifact_problems_name_ids_not_content(spec: Any) -> None:
    import json

    artifacts = _valid(spec)
    secret = "CONFIDENTIAL-VALUE-123"
    first = next(iter(artifacts))
    artifacts[first][0] = {**artifacts[first][0], "bogus": secret}
    del artifacts["kpis"]
    artifacts["invented"] = [{"x": 1}]
    parsed = parse_builder(json.dumps({"artifacts": artifacts}), spec, always)
    assert parsed.result is None
    text = " ".join(parsed.problems)
    assert "artifact kpis is missing" in text
    assert "artifact invented is not declared" in text
    assert f"{first} row 1: unknown columns ['bogus']" in text
    assert secret not in text and secret not in correction(parsed.problems)


def test_conditional_artifact_is_optional_when_its_condition_does_not_hold(spec: Any) -> None:
    import json

    artifacts = _valid(spec)
    del artifacts["kpis"]
    only_kpis_optional = parse_builder(
        json.dumps({"artifacts": artifacts}), spec, lambda a: a.id != "kpis"
    )
    assert isinstance(only_kpis_optional.result, Artifacts)


def test_clarification_needs_where_it_looked(spec: Any) -> None:
    ok = parse_builder(
        '{"clarification": {"questions": ["Q?"], "looked_in": ["intake"]}}', spec, always
    )
    assert isinstance(ok.result, Clarification) and ok.result.looked_in == ("intake",)
    bad = parse_builder('{"clarification": {"questions": ["Q?"], "looked_in": []}}', spec, always)
    assert bad.result is None and "looked_in" in bad.problems[0]
    too_many = parse_builder(
        '{"clarification": {"questions": ["1","2","3","4","5","6"], "looked_in": ["x"]}}',
        spec,
        always,
    )
    assert too_many.problems
    role = parse_builder(
        '{"clarification": {"questions": ["Q?"], "looked_in": ["x"], "addressed_role": "wizard"}}',
        spec,
        always,
        role_ids={"product_owner"},
    )
    assert "addressed_role" in role.problems[0]


def test_tool_request_and_wrong_shape(spec: Any) -> None:
    tool = parse_builder('{"tool": {"name": "kb", "arguments": {"q": "x"}}}', spec, always)
    assert tool.tool == {"name": "kb", "arguments": {"q": "x"}} and tool.result is None
    assert parse_builder('{"answer": 1}', spec, always).problems
    assert parse_builder("nothing", spec, always).problems == ("the answer is not one JSON object",)


def test_review_valid_maps_to_recommendation() -> None:
    raw = (
        '{"scores": {"CHK-T1-01": 3, "CHK-T1-02": 1},'
        ' "findings": [{"item": "CHK-T1-02", "text": "No unsafe-request boundary"},'
        ' {"item": null, "text": "Consistent overall"}],'
        ' "recommendation": {"status": "rework", "reason": "Boundaries missing",'
        ' "root_cause": "requirement"}}'
    )
    parsed = parse_review(raw, ITEMS, CAUSES)
    assert parsed.result == Recommendation(
        "rework",
        {"CHK-T1-01": 3, "CHK-T1-02": 1},
        ("CHK-T1-02: No unsafe-request boundary", "Consistent overall"),
        reason="Boundaries missing",
        root_cause="requirement",
        reviewer="model",
    )


@pytest.mark.parametrize(
    ("scores", "status", "cause", "problem"),
    [
        ({"CHK-T1-01": 3}, "pass", None, "scores missing items"),
        ({"CHK-T1-01": 3, "CHK-T1-02": 4}, "pass", None, "0 to 3"),
        ({"CHK-T1-01": 3, "CHK-T1-02": 2, "CHK-X": 1}, "pass", None, "unknown items"),
        ({"CHK-T1-01": 3, "CHK-T1-02": 2}, "terminate", None, "status must be one of"),
        ({"CHK-T1-01": 3, "CHK-T1-02": 2}, "rework", "luck", "root_cause must be one of"),
        ({"CHK-T1-01": 3, "CHK-T1-02": 2}, "pass", "design", "must be null unless"),
    ],
)
def test_review_rules(scores: dict[str, int], status: str, cause: str | None, problem: str) -> None:
    import json

    raw = json.dumps(
        {
            "scores": scores,
            "findings": [],
            "recommendation": {"status": status, "reason": "r", "root_cause": cause},
        }
    )
    parsed = parse_review(raw, ITEMS, CAUSES)
    assert parsed.result is None and any(problem in p for p in parsed.problems), parsed.problems
