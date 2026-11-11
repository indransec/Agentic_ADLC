"""T022: the T1 requirements agent builds on T0's evidence, gets failed controls back, and
addresses a rework comment (US2; FR-006)."""

import copy
import json
from collections.abc import Mapping, Sequence
from typing import Any

from adlc.policy.synthetic import load_synthetic_artifacts
from tests.support.grounded import grounded
from tests.support.orchestration import SYNTHETIC, person
from tests.support.pg import PlatformDatabase

SYN = load_synthetic_artifacts(SYNTHETIC)
T0_DRAFT = json.dumps({"artifacts": SYN["T0"]})
T1_DRAFT = json.dumps({"artifacts": SYN["T1"]})
REWORK_COMMENT = "Add a KPI for re-work rate on missing receipts"


def seen(messages: Sequence[Mapping[str, str]]) -> str:
    return "\n".join(m["content"] for m in messages)


class Capture:
    """A reply that records the request it answers."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.requests: list[str] = []

    def __call__(self, messages: Sequence[Mapping[str, str]]) -> str:
        self.requests.append(seen(messages))
        return self.answer


def bad_kpis() -> str:
    rows = copy.deepcopy(SYN["T1"])
    rows["kpis"][0]["target"] = "a lot better"
    return json.dumps({"artifacts": rows})


def to_t1(g: Any) -> tuple[str, Any]:
    h = g.h
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
    return usecase, h.active(usecase, "T1")


def test_t1_builds_on_t0_evidence(orch_template: PlatformDatabase) -> None:
    first = Capture(T1_DRAFT)
    with grounded(
        orch_template, {"t0-intake-agent": [T0_DRAFT], "t1-requirements-agent": [first]}
    ) as g:
        _, run = to_t1(g)
        assert run.state == "awaiting_sign_off", run.state
        request = first.requests[0]
        assert '<data source="evidence">' in request and "risk_classification" in request
        assert "confluence_search" in request and "jira_search" in request
        assert "sharepoint_search" not in request  # no SharePoint grounding at T1 (FR-002)
        failed = [c for c in run.control_results if not c["passed"]]
        assert failed == []


def test_a_failed_control_comes_back_with_its_reason(orch_template: PlatformDatabase) -> None:
    retry = Capture(T1_DRAFT)
    with grounded(
        orch_template, {"t0-intake-agent": [T0_DRAFT], "t1-requirements-agent": [bad_kpis(), retry]}
    ) as g:
        _, run = to_t1(g)
        g.h.drain()
        run = g.h.run(run.run_id)
        assert run.state == "awaiting_sign_off" and run.auto_retries == 1
        assert '<data source="failed_controls">' in retry.requests[0]
        assert "CTL-T1-02" in retry.requests[0]


def test_rework_comment_reaches_the_next_build(orch_template: PlatformDatabase) -> None:
    rebuild = Capture(T1_DRAFT)
    with grounded(
        orch_template, {"t0-intake-agent": [T0_DRAFT], "t1-requirements-agent": [T1_DRAFT, rebuild]}
    ) as g:
        h = g.h
        usecase, run = to_t1(g)
        h.service.decide(
            person("product_owner"),
            run.run_id,
            "rework",
            comment=REWORK_COMMENT,
            root_cause="requirement",
            reason="the reviewer missed it",
            fields={"owner_comment": REWORK_COMMENT},
        )
        h.drain()
        assert h.active(usecase, "T1").run_number == 2
        assert REWORK_COMMENT in rebuild.requests[0]


def test_t1_is_told_the_parameters_its_controls_check(orch_template: PlatformDatabase) -> None:
    """008: the resolved run parameters (e.g. the minimum number of scenarios) are in the request."""
    first = Capture(T1_DRAFT)
    with grounded(
        orch_template, {"t0-intake-agent": [T0_DRAFT], "t1-requirements-agent": [first]}
    ) as g:
        to_t1(g)
    request = first.requests[0]
    block = request.split('<data source="parameters">\n', 1)[1].split("\n</data>")[0]
    values = json.loads(block)
    assert values["test_scenarios_min"] == 30 and values["autonomy_level_max"] == 3  # medium
