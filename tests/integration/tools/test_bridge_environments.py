"""T013, T014 (US1): pilot environments through the tool gate, the run token and the bridge;
refusals at the gate and at the server; every call recorded (FR-002, FR-004, FR-008; SC-001,
SC-002)."""

from adlc.agents.tools import ToolOutput, ToolRefused
from tests.support.tools import call, token

from .conftest import Tools

CANDIDATE_FILES = {"routing_rules.yaml": "x: 1", "instructions.md": "Candidate."}


def test_t3_creates_dev_reads_status_and_infra_and_tears_down(tools: Tools) -> None:
    package = tools.pilot.add_package()
    t3 = tools.gate(
        "T3", "pilot_env_create", "pilot_env_status", "pilot_env_delete", "pilot_env_infra"
    )
    created = t3("pilot_env_create", {"package_hash": package, "environment": "test"})
    assert isinstance(created, ToolOutput), created
    assert '"environment": "dev"' in created.text and package in created.text
    assert (
        tools.pilot.hosts["dev"].running is not None and tools.pilot.hosts["test"].running is None
    )
    status = t3("pilot_env_status", {"environment": "dev"})
    assert isinstance(status, ToolOutput) and '"running": true' in status.text
    infra = t3("pilot_env_infra", {"environment": "test"})
    assert isinstance(infra, ToolOutput) and '"template_version": "1.0.0"' in infra.text
    deleted = t3("pilot_env_delete")
    assert isinstance(deleted, ToolOutput) and tools.pilot.hosts["dev"].running is None
    again = t3("pilot_env_delete")
    assert isinstance(again, ToolOutput) and again.text.startswith(
        "pilot_env_delete failed: not found"
    )
    calls = tools.calls()
    assert [c["outcome"] for c in calls] == ["ok", "ok", "ok", "ok", "failed"]
    assert {c["scope"] for c in calls} == {"dev", "read"}
    assert [r["kind"] for r in tools.results()] == ["environment", "environment"]


def test_t4_test_environment_runs_the_candidate_only(tools: Tools) -> None:
    candidate = tools.pilot.add_package(CANDIDATE_FILES)
    other = tools.pilot.add_package()
    t4 = tools.gate("T4", "pilot_env_create")
    refused = t4("pilot_env_create")  # no candidate package yet: refused before any call
    assert isinstance(refused, ToolOutput) and "refused: no candidate hash" in refused.text
    assert tools.pilot.hosts["test"].calls == []
    tools.evidence.records["T3"] = {"candidate_package": {"sha256": candidate}}
    created = t4("pilot_env_create", {"package_hash": other})
    assert isinstance(created, ToolOutput), created
    assert tools.pilot.hosts["test"].running["package_hash"] == candidate  # type: ignore[index]
    assert tools.pilot.hosts["dev"].running is None


def test_out_of_scope_calls_never_reach_the_pilot(tools: Tools) -> None:
    package = tools.pilot.add_package()
    t3 = tools.gate("T3", "pilot_env_create", "cd_deploy")
    # T3 has no deploy scope: refused at the gate, recorded, nothing sent
    refused = t3("cd_deploy")
    assert isinstance(refused, ToolRefused) and "not in scope" in refused.reason
    # acting for another run is refused too
    other = t3("pilot_env_create", {"package_hash": package}, as_run="UC-0002/T3/run-1")
    assert isinstance(other, ToolRefused)
    assert tools.pilot.hosts["dev"].calls == [] and tools.pilot.hosts["prod-sim"].calls == []
    assert [c["outcome"] for c in tools.calls()] == ["refused", "refused"]
    assert all(c["reason"] for c in tools.calls())


def test_the_server_refuses_calls_that_skip_the_gate(tools: Tools) -> None:
    package = tools.pilot.add_package()
    base = tools.bridge_url
    args = {"package_hash": package}
    # a T3 token used for test, a token without the environment, an expired one, a wrong key
    cases = [
        token(["mcp:pilot_env:dev"], bound={"environment": "test"}),
        token(["mcp:pilot_env:dev"]),
        token(["mcp:pilot_env:dev"], bound={"environment": "dev"}, now=0),
        token(["mcp:pilot_env:dev"], bound={"environment": "dev"}, key="w" * 40),
    ]
    for bad in cases:
        failed, text = call(base, "pilot_env", "create", args, bad)
        assert failed and text.startswith("not permitted"), text
    assert tools.pilot.hosts["dev"].calls == [] and tools.pilot.hosts["test"].calls == []
    audit = (tools.bridge_dir / "records" / "calls.jsonl").read_text()
    assert audit.count('"refused"') == 4 and package not in audit


def test_infra_resources(tools: Tools) -> None:
    import anyio
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def read(run_token: str) -> str:
        async with (
            httpx.AsyncClient(headers={"Authorization": f"Bearer {run_token}"}, timeout=10) as http,
            streamable_http_client(f"{tools.bridge_url}/mcp/pilot_env/", http_client=http) as (
                r,
                w,
                _,
            ),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            listed = await session.list_resources()
            assert {str(x.uri) for x in listed.resources} == {
                "infra://dev",
                "infra://test",
                "infra://prod-sim",
            }
            got = await session.read_resource("infra://prod-sim")  # type: ignore[arg-type]
            return "".join(getattr(c, "text", "") for c in got.contents)

    text = anyio.run(read, token(["mcp:pilot_env:read"]))
    assert '"environment": "prod-sim"' in text and '"environment": "dev"' not in text
    try:
        anyio.run(read, token(["mcp:pilot_env:dev"]))
    except Exception as exc:  # the resource read is refused without the read scope
        assert "not permitted" in repr(exc)
    else:
        raise AssertionError("read without the read scope was not refused")
