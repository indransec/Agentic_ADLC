"""T030 (US4; FR-017, FR-018, SC-006): only the hash authorised at T6 deploys, checked at the
platform and at the server; the split moves and rolls back; the kill switch stops prod-sim."""

import json
from typing import Any

from adlc.agents.tools import ToolOutput, ToolRefused
from tests.support.tools import call, token

from .conftest import Tools


def output(reply: object) -> dict[str, Any]:
    assert isinstance(reply, ToolOutput), reply
    loaded: dict[str, Any] = json.loads(reply.text)
    return loaded


def authorised(tools: Tools) -> tuple[str, str]:
    stable = tools.pilot.add_package()
    candidate = tools.pilot.add_package({"routing_rules.yaml": "x", "instructions.md": "v2"})
    tools.pilot.hosts["prod-sim"].stable = stable
    tools.evidence.records["T3"] = {"candidate_package": {"sha256": candidate}}
    tools.evidence.records["T6"] = {
        "deployment_package": [{"item": "package", "version": "2", "sha256": candidate}]
    }
    return stable, candidate


def test_only_the_authorised_hash_deploys(tools: Tools) -> None:
    stable = tools.pilot.add_package()
    other = tools.pilot.add_package({"routing_rules.yaml": "y", "instructions.md": "rogue"})
    t7 = tools.gate("T7", "cd_deploy")
    refused = t7("cd_deploy", {"package_hash": other})  # no T6 authorisation yet
    assert isinstance(refused, ToolOutput) and "refused: no authorised hash" in refused.text
    assert tools.pilot.hosts["prod-sim"].candidate is None
    _, candidate = authorised(tools)
    deployed = output(t7("cd_deploy", {"package_hash": other}))  # the model's hash is ignored
    assert deployed["package_hash"] == candidate
    assert tools.pilot.hosts["prod-sim"].candidate == candidate
    # straight to the server: no authorised hash in the token, or a token for another scope
    for bad in (token(["mcp:cd:deploy"]), token(["mcp:traffic_manager:write"])):
        failed, text = call(tools.bridge_url, "cd", "deploy", {}, bad)
        assert failed and text.startswith("not permitted")
    assert stable != candidate
    assert [r["kind"] for r in tools.results()] == ["deploy"]
    outcomes = [c["outcome"] for c in tools.calls()]
    assert outcomes == ["refused", "ok"]


def test_split_promotion_rollback_and_kill_switch(tools: Tools) -> None:
    stable, candidate = authorised(tools)
    t7 = tools.gate("T7", "cd_deploy", "traffic_manager_set", "traffic_manager_rollback")
    output(t7("cd_deploy"))
    assert output(t7("traffic_manager_set", {"mode": "shadow"}))["mode"] == "shadow"
    canary = output(t7("traffic_manager_set", {"mode": "canary", "share": 0.2}))
    assert (canary["mode"], canary["share"]) == ("canary", 0.2)
    full = output(t7("traffic_manager_set", {"mode": "full"}))
    assert (full["mode"], full["stable"]) == ("full", candidate)  # promoted
    back = output(t7("traffic_manager_rollback"))
    assert back["restored_stable"] == stable and tools.pilot.hosts["prod-sim"].stable == stable
    t8 = tools.gate("T8", "kill_switch_invoke")
    assert output(t8("kill_switch_invoke", {"reason": "drift"}))["active"] is True
    again = t8("kill_switch_invoke", {"reason": "again"})
    assert isinstance(again, ToolOutput) and "refused" in again.text
    assert tools.pilot.hosts["prod-sim"].killed is True
    kinds = [r["kind"] for r in tools.results()]
    assert kinds == ["deploy", "traffic", "traffic", "traffic", "traffic", "kill_switch"]
    t3 = tools.gate("T3", "kill_switch_invoke")
    assert isinstance(t3("kill_switch_invoke", {"reason": "x"}), ToolRefused)  # not T3's scope
