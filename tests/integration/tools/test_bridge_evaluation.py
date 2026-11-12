"""T027 (US3; FR-013 to FR-016, SC-004, SC-005): harness, red-team and scan against the candidate
in the test environment, stored as evidence; repeatable; the degraded model scores lower; the leak
is caught only when it is on."""

import json
from typing import Any

from adlc.agents.tools import ToolOutput

from .conftest import Tools


def output(reply: object) -> dict[str, Any]:
    assert isinstance(reply, ToolOutput), reply
    loaded: dict[str, Any] = json.loads(reply.text)
    return loaded


def candidate_in_test(tools: Tools, terminal: str, *names: str) -> tuple[str, Any]:
    candidate = tools.pilot.add_package({"routing_rules.yaml": "x", "instructions.md": "candidate"})
    tools.evidence.records["T3"] = {"candidate_package": {"sha256": candidate}}
    gate = tools.gate(terminal, "pilot_env_create", *names)
    output(gate("pilot_env_create"))
    return candidate, gate


def test_harness_is_repeatable_stored_and_sees_the_degraded_model(tools: Tools) -> None:
    candidate, t4 = candidate_in_test(tools, "T4", "dataset_registry_list", "harness_run")
    listed = output(t4("dataset_registry_list"))["datasets"]
    assert {d["id"] for d in listed} == {"golden", "pii"}
    first = output(t4("harness_run", {"dataset_id": "golden"}))
    second = output(t4("harness_run", {"dataset_id": "golden"}))
    assert first["package_hash"] == candidate and first["metrics"] == second["metrics"]
    assert (
        first["metrics"]["field_accuracy"]["team"] == 1.0 and first["metrics"]["recall_p1"] == 1.0
    )
    assert first["metrics"]["rai"]["tokens"] > 0
    tools.pilot.hosts["test"].mode = "degraded"
    degraded = output(t4("harness_run", {"dataset_id": "golden"}))
    drop = (
        first["metrics"]["field_accuracy"]["team"] - degraded["metrics"]["field_accuracy"]["team"]
    )
    assert drop >= 0.2
    results = tools.results()
    assert [r["kind"] for r in results] == ["environment", "harness", "harness", "harness"]
    assert all(r["package_hash"] == candidate for r in results)
    text = json.dumps([r["result"] for r in results])
    assert "Problem 1 with a service" not in text  # no incident text in evidence
    unknown = t4("harness_run", {"dataset_id": "made-up"})
    assert isinstance(unknown, ToolOutput) and "not in the registry" in unknown.text


def test_harness_refuses_when_test_does_not_run_the_candidate(tools: Tools) -> None:
    candidate, t4 = candidate_in_test(tools, "T4", "harness_run")
    tools.pilot.hosts["test"].running["package_hash"] = tools.pilot.add_package()  # type: ignore[index]
    reply = t4("harness_run", {"dataset_id": "golden"})
    assert isinstance(reply, ToolOutput) and "does not run the candidate" in reply.text


def test_redteam_and_scan_with_and_without_the_leak(tools: Tools) -> None:
    candidate, t5 = candidate_in_test(tools, "T5", "redteam_harness_run", "dlp_scanner_run")
    clean = output(t5("redteam_harness_run"))
    assert clean["suite_version"] == "1.0.0"
    assert set(clean["by_category"]) == {
        "prompt_injection",
        "jailbreak",
        "pii_extraction",
        "abusive_input",
    }
    assert all(c["rate"] == 0.0 for c in clean["by_category"].values())
    assert clean["by_category"]["pii_extraction"]["attempts"] == 15
    scan = output(t5("dlp_scanner_run", {"dataset_id": "pii"}))
    assert scan["rate"] == 0.0 and scan["findings"] == []
    tools.pilot.hosts["test"].mode = "leak"
    leaking = output(t5("redteam_harness_run", {"categories": ["pii_extraction"]}))
    assert leaking["by_category"]["pii_extraction"]["rate"] > 0
    scan = output(t5("dlp_scanner_run", {"dataset_id": "pii"}))
    planted = scan["planted_in_answers"]
    assert planted["planted"] == planted["exposed"] == 10  # every planted value found (SC-005)
    assert scan["rate"] == 1.0 and all("***@example.com" in f["masked"] for f in scan["findings"])
    assert "person1@example.com" not in json.dumps(scan)
    tools.pilot.hosts["test"].mode = "obedient"
    obeyed = output(t5("redteam_harness_run", {"categories": ["prompt_injection"]}))
    assert obeyed["by_category"]["prompt_injection"]["successes"] == 5  # PI-01 carriers only
