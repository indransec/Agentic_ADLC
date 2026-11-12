"""T008: the platform side of the 010 tools: only the model's declared arguments pass, bound values
come from the run and real evidence, the token carries them, and every call is recorded."""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from adlc.agents.mcp_tools import BoundValues, McpTool, scope_for
from adlc.agents.tools import ToolContext
from adlc.orchestration.interfaces import EvalContext
from adlc.policy.evidence import Answer, Evidence
from adlc.policy.values import NOT_AVAILABLE
from adlc.tools.catalogue import CATALOGUE, ToolSpec
from adlc.tools.client import ToolUnavailable
from adlc.tools.token import verify

KEY = "k" * 40
CANDIDATE = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
REFS = {"candidate_hash": "T3.candidate_package", "authorised_hash": "T6.deployment_package"}


def context(terminal: str = "T3", scopes: tuple[str, ...] = ("mcp:pilot_env:dev",)) -> ToolContext:
    spec = {"terminal": {"authorities": {"tool_scopes": [*scopes, "other:thing"]}}}
    return ToolContext(f"UC-0001/{terminal}/run-1", "UC-0001", terminal, spec, 2, 3)


@dataclass
class FakeEvidence:
    records: Mapping[str, Any]
    synthetic: bool = False

    def get(self, source: str, context: EvalContext) -> Answer:
        if source not in self.records:
            return NOT_AVAILABLE
        return Evidence(self.records[source], source, self.synthetic)


@dataclass
class FakeClient:
    answer: tuple[bool, str] = (False, '{"ok": true}')
    calls: list[dict[str, Any]] = field(default_factory=list)
    down: bool = False

    def __call__(
        self, host: str, server: str, tool: str, arguments: Mapping[str, Any], token: str
    ) -> tuple[bool, str]:
        if self.down:
            raise ToolUnavailable(server)
        self.calls.append(
            {"host": host, "server": server, "tool": tool, "args": dict(arguments), "token": token}
        )
        return self.answer


@dataclass
class FakeRecords:
    calls: list[dict[str, Any]] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)

    def call(
        self,
        context: ToolContext,
        tool: ToolSpec,
        scope: str,
        arguments_sha256: str,
        outcome: str,
        reason: str,
        duration_ms: int,
    ) -> int:
        self.calls.append(
            {
                "tool": tool.full_name,
                "scope": scope,
                "outcome": outcome,
                "reason": reason,
                "args": arguments_sha256,
            }
        )
        return len(self.calls)

    def result(
        self, call_id: int, context: ToolContext, kind: str, package: str | None, result: Any
    ) -> None:
        self.results.append({"call": call_id, "kind": kind, "package": package, "result": result})


def tool(
    name: str, evidence: FakeEvidence | None = None, client: FakeClient | None = None
) -> tuple[McpTool, FakeClient, FakeRecords]:
    client = client or FakeClient()
    records = FakeRecords()
    bound = BoundValues(evidence or FakeEvidence({}), REFS)
    return McpTool(CATALOGUE.tools[name], "bridge", client, KEY, bound, records), client, records


def test_only_declared_arguments_pass_and_the_branch_is_bound() -> None:
    t, client, records = tool("git_write")
    ctx = context(scopes=("mcp:git:branch_write",))
    t.call(
        {"files": {"instructions.md": "x"}, "message": "m", "branch": "main", "run_id": "other"},
        ctx,
    )
    sent = client.calls[0]
    assert set(sent["args"]) == {"files", "message"}
    claims = verify(sent["token"], KEY, scope="mcp:git:branch_write", now=t.now())
    assert claims.bound == {"branch": "uc/UC-0001/T3/run-1"}
    assert claims.run_id == ctx.run_id and claims.attempt == 2
    assert claims.scopes == ("mcp:git:branch_write",)  # only mcp: scopes of the pinned spec
    assert records.calls[0]["outcome"] == "ok" and records.results == []


def test_environment_comes_from_the_terminals_single_environment_scope() -> None:
    create = CATALOGUE.tools["pilot_env_create"]
    assert scope_for(create, context(scopes=("mcp:pilot_env:dev",)).spec) == "dev"
    assert scope_for(create, context("T4", ("mcp:pilot_env:test",)).spec) == "test"
    assert (
        scope_for(create, context(scopes=("mcp:pilot_env:dev", "mcp:pilot_env:test")).spec) is None
    )
    t, client, records = tool("pilot_env_create")
    t.call({"package_hash": CANDIDATE}, context(scopes=()))
    assert client.calls == [] and records.calls[0]["outcome"] == "refused"
    t.call({"package_hash": CANDIDATE, "environment": "test"}, context())
    claims = verify(client.calls[0]["token"], KEY, scope="mcp:pilot_env:dev", now=t.now())
    assert claims.bound["environment"] == "dev" and "environment" not in client.calls[0]["args"]


def test_candidate_and_authorised_hashes_come_from_real_evidence() -> None:
    evidence = FakeEvidence(
        {
            "T3": {"candidate_package": {"package_uri": "x", "sha256": CANDIDATE}},
            "T6": {
                "deployment_package": [
                    {"item": "pkg", "sha256": CANDIDATE},
                    {"item": "cfg", "sha256": OTHER},
                ]
            },
        }
    )
    t, client, records = tool(
        "cd_deploy", evidence, FakeClient((False, f'{{"package_hash": "{CANDIDATE}"}}'))
    )
    t.call({"package_hash": OTHER}, context("T7", ("mcp:cd:deploy",)))
    claims = verify(
        client.calls[0]["token"],
        KEY,
        scope="mcp:cd:deploy",
        now=t.now(),
        required=("authorised_hash",),
    )
    assert claims.bound["authorised_hash"] == CANDIDATE and client.calls[0]["args"] == {}
    assert records.results == [
        {"call": 1, "kind": "deploy", "package": CANDIDATE, "result": {"package_hash": CANDIDATE}}
    ]


def test_no_or_ambiguous_or_synthetic_evidence_binds_nothing() -> None:
    cases = [
        FakeEvidence({"T3": {"candidate_package": {"sha256": CANDIDATE}}}),  # no T6 row
        FakeEvidence(
            {
                "T3": {"candidate_package": {"sha256": CANDIDATE}},
                "T6": {"deployment_package": [{"sha256": OTHER}]},
            }
        ),
        FakeEvidence(
            {
                "T3": {"candidate_package": {"sha256": CANDIDATE}},
                "T6": {"deployment_package": [{"sha256": CANDIDATE}, {"sha256": CANDIDATE}]},
            }
        ),
        FakeEvidence(
            {
                "T3": {"candidate_package": {"sha256": CANDIDATE}},
                "T6": {"deployment_package": [{"sha256": CANDIDATE}]},
            },
            synthetic=True,
        ),
    ]
    for evidence in cases:
        t, client, records = tool("cd_deploy", evidence)
        reply = t.call({}, context("T7", ("mcp:cd:deploy",)))
        assert client.calls == [] and "refused: no authorised hash" in reply
        assert records.calls[0]["outcome"] == "refused"


def test_errors_unavailable_and_gate_refusals_are_recorded() -> None:
    t, _, records = tool(
        "cd_status", client=FakeClient((True, "not permitted: scope mcp:cd:read not granted"))
    )
    assert "refused" in t.call({}, context("T7", ("mcp:cd:read",)))
    t2, _, records2 = tool("cd_status", client=FakeClient(down=True))
    assert "unavailable" in t2.call({}, context("T7", ("mcp:cd:read",)))
    t3, _, records3 = tool("cd_status")
    t3.refused(context("T7"), "not permitted: mcp:cd:read")
    assert [r["outcome"] for r in records.calls + records2.calls + records3.calls] == [
        "refused",
        "unavailable",
        "refused",
    ]
    assert all(r["reason"] for r in records.calls + records2.calls + records3.calls)


def test_describe_shows_only_model_arguments() -> None:
    t, _, _ = tool("harness_run")
    assert t.describe()["arguments"] == {"dataset_id": "a dataset id from the registry"}


def test_long_lists_are_stored_not_shown() -> None:
    """011: the agent sees the size of a long list; the full result is recorded."""
    cases = [{"case_id": f"C-{n}"} for n in range(50)]
    answer = json.dumps(
        {"package_hash": CANDIDATE, "catalogue": {"task_success_rate": 1.0}, "cases": cases}
    )
    evidence = FakeEvidence({"T3": {"candidate_package": {"sha256": CANDIDATE}}})
    t, _, records = tool("harness_run", evidence, FakeClient((False, answer)))
    seen = json.loads(t.call({"dataset_id": "golden"}, context("T4", ("mcp:harness:run",))))
    assert seen["cases"] == {"count": 50, "stored": "import or cite it by result_id"}
    assert seen["catalogue"] == {"task_success_rate": 1.0}
    assert len(records.results[0]["result"]["cases"]) == 50
