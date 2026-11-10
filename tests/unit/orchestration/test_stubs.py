"""T017: scriptable stubs implement the interfaces (research R-10)."""

from typing import Any

from adlc.orchestration.interfaces import (
    Artifacts,
    BudgetExceeded,
    BuildContext,
    Clarification,
    EvalContext,
    Recommendation,
    ReviewContext,
)
from adlc.orchestration.stubs import StubAgent, StubPolicy, StubReviewer


def _build(spec: Any, terminal: str = "T9") -> BuildContext:
    return BuildContext("UC-0001/T9/run-1", terminal, spec, {}, {}, {}, (), 1)


def test_agent_builds_every_artifact(pinned: dict[str, Any]) -> None:
    result = StubAgent().build(_build(pinned["T1"], "T1"))
    assert isinstance(result, Artifacts)
    assert result.artifacts["kpis"] == [
        {
            c: f"{c} (stub)"
            for c in ("kpi_id", "kpi", "baseline", "target", "unit", "measurement_source")
        }
    ]


def test_agent_scripts(pinned: dict[str, Any]) -> None:
    question = Clarification(("Which channel?",))
    agent = StubAgent(
        {
            "T9": {
                1: question,
                2: {"change_impact_assessment": {"reentry_terminal": "T2"}},
                3: BudgetExceeded(),
            }
        }
    )
    assert agent.build(_build(pinned["T9"])) == question
    second = agent.build(_build(pinned["T9"]))
    assert isinstance(second, Artifacts)
    assert second.artifacts["change_impact_assessment"][0]["reentry_terminal"] == "T2"
    assert isinstance(agent.build(_build(pinned["T9"])), BudgetExceeded)
    assert agent.calls["T9"] == 3


def test_reviewer_defaults_and_scripts() -> None:
    context = ReviewContext("UC-0001/T1/run-1", "T1", ("CHK-1", "CHK-2"), {}, ())
    assert StubReviewer().review(context) == Recommendation("pass", {"CHK-1": 1, "CHK-2": 1})
    scripted = StubReviewer({"T1": {1: Recommendation("rework")}})
    assert scripted.review(context) == Recommendation("rework")


def test_policy_defaults_and_scripts() -> None:
    policy = StubPolicy({("T1", "PRE-T1-01"): False})
    assert not policy.evaluate("x", EvalContext("T1", "PRE-T1-01")).passed
    assert policy.evaluate("x", EvalContext("T1", "PRE-T1-02")).passed
    assert policy.authorize("agent", "write", "T1.artifacts", EvalContext("T1", "a"))
    assert policy.calls == [("T1", "PRE-T1-01"), ("T1", "PRE-T1-02")]
