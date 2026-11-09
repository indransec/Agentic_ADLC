"""T030: L5 version rules against a git baseline (research R-10; V-24, V-25)."""

import subprocess
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from adlc.spec_toolkit.findings import Finding
from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.rules import Context, validate
from adlc.spec_toolkit.rules.versioning import BumpLevel, compare
from tests.support.spec_fixtures import build_bundle

T0 = "terminals/T0.yaml"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = build_bundle(tmp_path)
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "baseline")
    return root


def _edit(root: Path, rel: str, change: "dict[str, object]") -> None:
    yaml = YAML()
    path = root / rel
    data = yaml.load(path.read_text())
    for pointer, value in change.items():
        node = data
        keys = pointer.strip("/").split("/")
        for key in keys[:-1]:
            node = node[int(key)] if isinstance(node, list) else node[key]
        last = keys[-1]
        if value is None:
            del node[last]
        elif isinstance(node, list):
            node[int(last)] = value
        else:
            node[last] = value
    with path.open("w") as handle:
        yaml.dump(data, handle)


def _l5(root: Path, ref: str | None = "main") -> list[Finding]:
    ctx = Context(load_bundle(root), baseline_ref=ref, use_git_baseline=ref is not None)
    return [f for f in validate(ctx) if f.level == "L5"]


@pytest.mark.parametrize(
    ("change", "level"),
    [
        ({"/terminal/controls/automated/0/description": "reworded"}, BumpLevel.PATCH),
        ({"/terminal/actors/subagents/0/responsibility": "x"}, BumpLevel.PATCH),
        ({"/terminal/outcome_model/pass/emits": ["risk_tier", "usecase_id"]}, BumpLevel.MINOR),
        ({"/terminal/outcome_model/pass/route": "lifecycle_closed"}, BumpLevel.MAJOR),
        ({"/terminal/timeline/reminder_after": "3d"}, BumpLevel.MAJOR),
        ({"/terminal/actors/subagents": None}, BumpLevel.MAJOR),
    ],
)
def test_compare_levels(repo: Path, change: "dict[str, object]", level: BumpLevel) -> None:
    yaml = YAML(typ="safe")
    before = yaml.load((repo / T0).read_text())
    _edit(repo, T0, change)
    after = yaml.load((repo / T0).read_text())
    assert compare(before, after) == level


def test_unchanged_is_clean(repo: Path) -> None:
    assert [f for f in _l5(repo) if f.severity != "info"] == []


def test_change_without_bump_is_v24(repo: Path) -> None:
    _edit(repo, T0, {"/terminal/outcome_model/pass/route": "lifecycle_closed"})
    findings = _l5(repo)
    assert any(f.rule_id == "V-24" and f.file == T0 and f.severity == "error" for f in findings)


def test_too_small_bump_is_v24(repo: Path) -> None:
    _edit(
        repo,
        T0,
        {
            "/terminal/outcome_model/pass/route": "lifecycle_closed",
            "/terminal/metadata/version": "1.0.1",
        },
    )
    messages = [f.message for f in _l5(repo) if f.rule_id == "V-24"]
    assert messages and "major" in messages[0]


def test_sufficient_bump_passes(repo: Path) -> None:
    _edit(
        repo,
        T0,
        {
            "/terminal/outcome_model/pass/route": "lifecycle_closed",
            "/terminal/metadata/version": "2.0.0",
        },
    )
    assert [f for f in _l5(repo) if f.severity == "error"] == []


def test_version_decrease_is_v25(repo: Path) -> None:
    _edit(repo, T0, {"/terminal/metadata/version": "0.9.0"})
    assert any(f.rule_id == "V-25" and f.file == T0 for f in _l5(repo))


def test_catalogue_change_needs_bump(repo: Path) -> None:
    _edit(repo, "shared/guardrails.yaml", {"/guardrails/0/values/high": 0.005})
    assert any(f.rule_id == "V-24" and f.file == "shared/guardrails.yaml" for f in _l5(repo))


def test_new_file_passes(repo: Path) -> None:
    (repo / "checklists" / "t9.yaml").write_text(
        'checklist: t9\nversion: "1.0.0"\nitems:\n  - {id: CHK-T9-01, text: x}\n'
    )
    assert [f for f in _l5(repo) if f.file == "checklists/t9.yaml"] == []


def test_missing_ref_warns_once(repo: Path) -> None:
    findings = _l5(repo, ref="no-such-branch")
    assert [(f.rule_id, f.severity) for f in findings] == [("V-24", "warning")]


def test_no_baseline_skips(repo: Path) -> None:
    _edit(repo, T0, {"/terminal/outcome_model/pass/route": "lifecycle_closed"})
    assert _l5(repo, ref=None) == []
