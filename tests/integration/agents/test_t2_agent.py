"""T024: the T2 architect agent designs against the requirements, the approved tools and the
reference architectures, and cites them (US3; FR-002, FR-004)."""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from adlc.agents.replay import Planned
from adlc.policy.synthetic import load_synthetic_artifacts
from tests.support.grounded import grounded
from tests.support.orchestration import SYNTHETIC
from tests.support.pg import PlatformDatabase

SYN = load_synthetic_artifacts(SYNTHETIC)
REFERENCE = "ra-tool-using-agent.md"


def answer(terminal: str, citations: list[dict[str, Any]] | None = None) -> str:
    out: dict[str, Any] = {"artifacts": SYN[terminal]}
    if citations:
        out["citations"] = citations
    return json.dumps(out)


def test_t2_designs_cites_and_passes_its_controls(orch_template: PlatformDatabase) -> None:
    requests: list[str] = []

    def design(messages: Sequence[Mapping[str, str]]) -> str:
        requests.append("\n".join(m["content"] for m in messages))
        return answer(
            "T2",
            [
                {
                    "artifact": "system_architecture",
                    "row": None,
                    "source": "arch_repo",
                    "document": REFERENCE,
                    "section": "Pattern",
                }
            ],
        )

    replies: dict[str, list[Planned]] = {
        "t0-intake-agent": [answer("T0")],
        "t1-requirements-agent": [answer("T1")],
        "t2-architect-agent": [
            json.dumps(
                {
                    "tool": {
                        "name": "arch_repo_search",
                        "arguments": {"query": "tool-using agent human approval"},
                    }
                }
            ),
            design,
        ],
    }
    with grounded(orch_template, replies) as g:
        h = g.h
        usecase = h.submit()
        h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
        h.pass_run(h.active(usecase, "T1").run_id)
        run = h.active(usecase, "T2")
        assert run.state == "awaiting_sign_off", run.state
        assert [c["id"] for c in run.control_results if not c["passed"]] == []
        (cited,) = h.sql(
            "SELECT source, document, section FROM run.artifact_citation WHERE run_id = :r",
            r=run.run_id,
        )
        assert tuple(cited) == ("arch_repo", REFERENCE, "Pattern")
        listed = requests[0]
        assert "arch_repo_search" in listed and "mcp_registry_search" in listed
        assert "sharepoint_search" not in listed  # in tool scopes, but no grounding (FR-002)
