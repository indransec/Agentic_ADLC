"""T020 (FR-010, research R-05): one repository per use case with the fill layout on main;
writes only on the bound branch, only fill files, within limits; a moved branch is refused; pull
requests are recorded; hooks never run."""

from pathlib import Path

import pytest

from adlc.tools.bridge.git_repo import GitRepos
from adlc.tools.bridge.records import Records
from adlc.tools.mcp_app import ToolFailure

LAYOUT = ["instructions.md", "routing_rules.yaml", "settings.yaml"]
BRANCH = "uc/UC-0001/T3/run-1"


def repos(tmp_path: Path) -> GitRepos:
    return GitRepos(tmp_path / "git", lambda: list(LAYOUT), Records(tmp_path / "records"))


def test_main_has_the_layout_and_the_branch_starts_from_it(tmp_path: Path) -> None:
    git = repos(tmp_path)
    main = git.list("UC-0001", BRANCH, "main", None)
    assert main["files"] == LAYOUT
    assert git.list("UC-0001", BRANCH, None, None)["commit"] == main["commit"]  # no branch yet
    wrote = git.write("UC-0001", BRANCH, {"instructions.md": "Route well."}, "fill", None)
    assert git.read("UC-0001", BRANCH, None, "instructions.md")["text"] == "Route well."
    assert git.read("UC-0001", BRANCH, "main", "instructions.md")["text"] == ""
    assert git.list("UC-0001", BRANCH, None, None)["commit"] == wrote["commit"]
    assert (tmp_path / "git" / "UC-0001.git").is_dir()


def test_refusals(tmp_path: Path) -> None:
    git = repos(tmp_path)
    for files, branch in (
        ({"instructions.md": "x"}, "main"),
        ({"../escape.md": "x"}, BRANCH),
        ({".github/workflows/ci.yml": "x"}, BRANCH),
        ({}, BRANCH),
        ({"instructions.md": "x" * 200_001}, BRANCH),
    ):
        with pytest.raises(ToolFailure):
            git.write("UC-0001", branch, files, "m", None)
    with pytest.raises(ToolFailure, match="only main or this run"):
        git.read("UC-0001", BRANCH, "uc/UC-0001/T3/run-2", "instructions.md")
    with pytest.raises(ToolFailure, match="not found"):
        git.read("UC-0001", BRANCH, None, "nope.md")


def test_a_moved_branch_is_refused_never_lost(tmp_path: Path) -> None:
    git = repos(tmp_path)
    first = git.write("UC-0001", BRANCH, {"instructions.md": "one"}, "1", None)["commit"]
    second = git.write("UC-0001", BRANCH, {"settings.yaml": "two"}, "2", first)["commit"]
    with pytest.raises(ToolFailure, match="branch head|branch moved"):
        git.write("UC-0001", BRANCH, {"instructions.md": "stale"}, "3", first)
    with pytest.raises(ToolFailure, match="branch head|branch moved"):
        git.write("UC-0001", BRANCH, {"instructions.md": "no parent"}, "4", None)
    head = git.list("UC-0001", BRANCH, None, None)["commit"]
    assert head == second
    assert git.read("UC-0001", BRANCH, None, "instructions.md")["text"] == "one"
    assert git.read("UC-0001", BRANCH, None, "settings.yaml")["text"] == "two"


def test_pull_requests_and_ci_files(tmp_path: Path) -> None:
    git = repos(tmp_path)
    with pytest.raises(ToolFailure):
        git.open_pull_request("UC-0001", "run", BRANCH, "t", "d")
    commit = git.write("UC-0001", BRANCH, {"instructions.md": "x"}, "m", None)["commit"]
    pr = git.open_pull_request("UC-0001", "UC-0001/T3/run-1", BRANCH, "Fill", "Default fill")
    assert pr == {"pull_request": "PR-1", "branch": BRANCH, "commit": commit, "target": "main"}
    assert Records(tmp_path / "records").read("pull_requests")[0]["commit"] == commit
    at, files = git.files_at("UC-0001", BRANCH, None)
    assert at == commit and files["instructions.md"] == "x" and set(files) == set(LAYOUT)
    other = git.write("UC-0001", "uc/UC-0001/T3/run-2", {"settings.yaml": "y"}, "m", None)
    with pytest.raises(ToolFailure, match="not on this run"):
        git.files_at("UC-0001", BRANCH, other["commit"])


def test_hooks_never_run(tmp_path: Path) -> None:
    git = repos(tmp_path)
    git.list("UC-0001", BRANCH, "main", None)  # creates the repository
    marker = tmp_path / "hook-ran"
    for hook in ("reference-transaction", "post-update", "post-commit"):
        script = tmp_path / "git" / "UC-0001.git" / "hooks" / hook
        script.write_text(f"#!/bin/sh\ntouch {marker}\n")
        script.chmod(0o755)
    git.write("UC-0001", BRANCH, {"instructions.md": "x"}, "m", None)
    assert not marker.exists()
