"""Rehearsed replies of the T3 agent (feature 014, research R-02; see ``common``)."""

import copy
import json
from collections.abc import Mapping
from typing import Any

from demo.rehearsed.common import FILL, SYN, Messages, Reply, all_outputs, output_of, tool


def create_dev(messages: Messages) -> str:
    return tool("pilot_env_create", {"package_hash": output_of(messages, "ci_run")["package_hash"]})


def t3_artifacts(coverage: float | None = None) -> Reply:
    def answer(messages: Messages) -> str:
        ci = output_of(messages, "ci_run")
        rows: dict[str, Any] = copy.deepcopy(dict(SYN["T3"]))
        rows["test_results"] = [{"suite": s, **v} for s, v in ci["tests"].items()]
        if coverage is not None:
            rows["test_results"][0]["coverage_pct"] = coverage
        rows["security_build_checks"] = [
            {"scan": s, "tool": "bandit" if s == "sast" else "pattern-scan", **v, "status": "pass"}
            for s, v in ci["scans"].items()
        ]
        rows["observability_check"] = ci["observability"]
        rows["candidate_package"] = [
            {"package_uri": f"pilot-registry://{ci['package_hash']}", "sha256": ci["package_hash"]}
        ]
        return json.dumps({"artifacts": rows})

    return answer


def t3_build(fill: Mapping[str, str] = FILL) -> list[Any]:
    return [
        tool("git_list"),
        tool(
            "git_write", {"files": dict(fill), "message": "Adapt the example fill to FR-01..FR-05"}
        ),
        tool("git_open_pull_request", {"title": "Use-case fill"}),
        tool("ci_run"),
        create_dev,
        tool("pilot_env_status", {"environment": "dev"}),
        t3_artifacts(),
    ]


ADAPTATION = (
    "\n\nFor the IT service desk: propose the category, priority and resolver group; never close "
    "an incident; security incidents stay with an analyst.\n"
)
READS = 5  # the template's fill points; a shorter list re-reads its first file


def _example_reader(index: int) -> Reply:
    def reply(messages: Messages) -> str:
        files = list(output_of(messages, "git_list")["files"])
        read = {o["path"] for o in all_outputs(messages, "git_read")}
        pending = [f for f in files if f not in read]
        return tool("git_read", {"path": pending[0] if pending else files[0]})

    return reply


def _write_adapted(messages: Messages) -> str:
    files = {o["path"]: o["text"] for o in all_outputs(messages, "git_read")}
    for name in files:
        if name.endswith(".md"):
            files[name] = files[name].rstrip("\n") + ADAPTATION
    return tool("git_write", {"files": files, "message": "Adapt the example fill to the use case"})


def t3_build_from_example() -> list[Any]:
    """The demo's T3 (014 rehearsal finding): like the real agent, adapt the example fill the
    branch starts with, so the real pilot's CI validates it (a fixed test fill does not)."""
    return [
        tool("git_list"),
        *(_example_reader(i) for i in range(READS)),
        _write_adapted,
        tool("git_open_pull_request", {"title": "Use-case fill"}),
        tool("ci_run"),
        create_dev,
        tool("pilot_env_status", {"environment": "dev"}),
        t3_artifacts(),
    ]
