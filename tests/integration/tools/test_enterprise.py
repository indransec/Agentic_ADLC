"""T035 (US6; FR-022): ITSM, CMDB, agent registry, IAM, GRC, control library and eval store keep
their records in the platform, scoped to the use case of the run token."""

import json
from typing import Any

from sqlalchemy import text

from adlc.agents.tools import ToolOutput, ToolRefused
from tests.support.tools import call, token

from .conftest import Tools


def output(reply: object) -> dict[str, Any]:
    assert isinstance(reply, ToolOutput), reply
    loaded: dict[str, Any] = json.loads(reply.text)
    return loaded


def read(
    tools: Tools, server: str, tool: str, args: dict[str, Any], usecase: str = "UC-0001"
) -> dict[str, Any]:
    run_token = token(
        [f"mcp:{server}:read"], run_id=f"{usecase}/T9/run-1", usecase_id=usecase, terminal_id="T9"
    )
    failed, body = call(tools.tools_url, server, tool, args, run_token)
    assert not failed, body
    loaded: dict[str, Any] = json.loads(body)
    return loaded


def test_itsm_registry_cmdb_and_iam(tools: Tools) -> None:
    t6 = tools.gate("T6", "servicenow_change_create")
    change = output(
        t6(
            "servicenow_change_create",
            {
                "summary": "Release v2",
                "window_start": "2026-11-20T09:00:00",
                "window_end": "2026-11-20T11:00:00",
                "risk": "low",
                "plan": "canary then full",
            },
        )
    )
    assert change == {"change_id": "CHG-1", "state": "new"}
    bad = t6(
        "servicenow_change_create",
        {
            "summary": "x",
            "window_start": "2026-11-20T11:00:00",
            "window_end": "2026-11-20T09:00:00",
            "risk": "low",
        },
    )
    assert isinstance(bad, ToolOutput) and "window_end must be after" in bad.text
    t7 = tools.gate("T7", "servicenow_incident_create", "agent_registry_write", "cmdb_write")
    assert (
        output(t7("servicenow_incident_create", {"summary": "Smoke failed", "severity": 2}))[
            "incident_id"
        ]
        == "INC-1"
    )
    agent = output(
        t7(
            "agent_registry_write",
            {"attributes": {"name": "Incident Triage Assistant", "version": "2", "status": "live"}},
        )
    )
    assert agent == {"agent_id": "AG-1", "version": 1}
    updated = output(
        t7("agent_registry_write", {"agent_id": "AG-1", "attributes": {"status": "retired"}})
    )
    assert updated == {"agent_id": "AG-1", "version": 2}
    bad_attr = t7("agent_registry_write", {"attributes": {"root_password": "x"}})
    assert isinstance(bad_attr, ToolOutput) and "attributes are" in bad_attr.text
    assert output(t7("cmdb_write", {"attributes": {"service": "triage"}}))["ci_id"] == "CI-1"
    records = read(tools, "servicenow", "read", {"kind": "change"})["records"]
    assert (
        records[0]["id"] == "CHG-1"
        and records[0]["terminal"] == "T6"
        and records[0]["risk"] == "low"
    )
    entry = read(tools, "agent_registry", "read", {"agent_id": "AG-1"})["records"][0]
    assert (entry["record_version"], entry["status"], entry["version"]) == (2, "retired", "2")
    evolving = tools.gate("T9", "iam_revoke", mode="evolve")  # 012: revocation is for retiring
    refused = evolving("iam_revoke", {"what": "tool_scopes", "reason": "not retiring"})
    assert isinstance(refused, ToolRefused) and "granted only in mode retire" in refused.reason
    t9 = tools.gate("T9", "iam_revoke", mode="retire")
    revoked = output(t9("iam_revoke", {"what": "tool_scopes", "reason": "retired"}))
    assert revoked == {"revocation_id": "REV-1", "identities": ["agent:AG-1"]}
    iam = read(tools, "iam", "read", {})
    assert (
        iam["identities"][0]["tool_scopes_revoked"] is True
        and iam["identities"][0]["identity_revoked"] is False
    )
    # another use case sees none of it
    assert read(tools, "servicenow", "read", {"kind": "change"}, usecase="UC-0002")["records"] == []
    assert read(tools, "agent_registry", "read", {}, usecase="UC-0002")["records"] == []
    with tools.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM tools.enterprise_record")).scalar_one() == 6


def test_grc_controls_and_eval_store(tools: Tools) -> None:
    t5 = tools.gate("T5", "grc_write", "control_library_read")
    assert (
        output(t5("grc_write", {"title": "Assurance", "report": "All controls met."}))["report_id"]
        == "GRC-1"
    )
    privacy = output(t5("control_library_read", {"topic": "privacy"}))["controls"]
    assert {c["id"] for c in privacy} == {"PRV-01", "PRV-02", "PRV-03"}
    missing = t5("control_library_read", {"control_id": "NOPE"})
    assert isinstance(missing, ToolOutput) and "not found" in missing.text
    # an evidence result the platform stored for this use case, then a note about it
    candidate = tools.pilot.add_package({"routing_rules.yaml": "x", "instructions.md": "c"})
    tools.evidence.records["T3"] = {"candidate_package": {"sha256": candidate}}
    t4 = tools.gate("T4", "pilot_env_create", "harness_run", "eval_store_write")
    output(t4("pilot_env_create"))
    output(t4("harness_run", {"dataset_id": "golden"}))
    note = output(t4("eval_store_write", {"note": "Accuracy meets the threshold."}))
    assert note == {"note_id": "NOTE-1"}
    store = read(tools, "eval_store", "read", {"kind": "harness"})
    assert [r["kind"] for r in store["results"]] == ["harness"]
    assert (
        store["results"][0]["package_hash"] == candidate
        and "rows" not in store["results"][0]["summary"]
    )
    assert store["notes"][0]["author"] == "agent"
    assert read(tools, "eval_store", "read", {}, usecase="UC-0002") == {"results": [], "notes": []}
