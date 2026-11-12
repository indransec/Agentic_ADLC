"""T022 (US2; FR-010 to FR-012, SC-003): a T3 run writes the fill on its branch, opens a pull
request and runs CI; the package hash is the pilot's own; the manifest and texts are retrievable."""

import json

from adlc.agents.tools import ToolOutput

from .conftest import Tools


def output(reply: object) -> dict[str, object]:
    assert isinstance(reply, ToolOutput), reply
    loaded: dict[str, object] = json.loads(reply.text)
    return loaded


def test_fill_to_package(tools: Tools) -> None:
    t3 = tools.gate(
        "T3",
        "git_list",
        "git_write",
        "git_open_pull_request",
        "ci_run",
        "artifact_store_read",
        "artifact_store_write",
        "prompt_registry_write",
    )
    listed = output(t3("git_list"))
    assert listed["files"] == ["instructions.md", "routing_rules.yaml", "settings.yaml"]
    files = {"instructions.md": "Route incidents.", "routing_rules.yaml": "a: 1"}
    wrote = output(t3("git_write", {"files": files, "message": "Default fill", "branch": "main"}))
    assert wrote["branch"] == "uc/UC-0001/T3/run-1"
    pr = output(t3("git_open_pull_request", {"title": "Default fill"}))
    assert pr["pull_request"] == "PR-1" and pr["commit"] == wrote["commit"]
    ci = output(t3("ci_run"))
    assert ci["commit"] == wrote["commit"] and all(c["passed"] for c in ci["checks"])  # type: ignore[attr-defined]
    package = str(ci["package_hash"])
    # the pilot built exactly the files on the branch, the same hash as its own build
    assert tools.pilot.builds[-1] == {**files, "settings.yaml": ""}
    assert package in tools.pilot.packages
    assert output(t3("artifact_store_read", {"package_hash": package}))["package_hash"] == package
    note = output(t3("artifact_store_write", {"name": "notes", "text": "Built from PR-1"}))
    prompt = output(t3("prompt_registry_write", {"text": "Route incidents."}))
    assert str(note["sha256"]).startswith("sha256:") and str(prompt["sha256"]).startswith("sha256:")
    results = tools.results()
    assert [r["kind"] for r in results] == ["ci"] and results[0]["package_hash"] == package
    assert all(c["outcome"] == "ok" for c in tools.calls())


def test_ci_failure_names_the_part_and_gives_no_hash(tools: Tools) -> None:
    t3 = tools.gate("T3", "git_write", "ci_run")
    output(t3("git_write", {"files": {"instructions.md": "only this"}, "message": "m"}))
    ci = output(t3("ci_run"))
    assert "package_hash" not in ci
    assert ci["checks"] == [
        {"name": "validate", "passed": False, "detail": "routing_rules: missing"}
    ]
    assert tools.results()[0]["package_hash"] is None
