"""T010: a package is a deterministic archive of the template and its fill (FR-003, SC-001)."""

import json
import shutil
from pathlib import Path

import pytest

from pilot_tools.build import BuildError, build, extract
from tests.conftest import DEFAULT_FILL, TEMPLATE, VARIANT_FILL


def test_same_input_same_hash_and_bytes(tmp_path: Path) -> None:
    first = build(TEMPLATE, DEFAULT_FILL, tmp_path / "a")
    second = build(TEMPLATE, DEFAULT_FILL, tmp_path / "b")
    assert first.package_hash == second.package_hash
    assert first.package_hash.startswith("sha256:") and len(first.package_hash) == 71
    assert first.archive.read_bytes() == second.archive.read_bytes()


def test_any_change_changes_the_hash(tmp_path: Path) -> None:
    base = build(TEMPLATE, DEFAULT_FILL, tmp_path / "r").package_hash
    assert build(TEMPLATE, VARIANT_FILL, tmp_path / "r").package_hash != base
    template = tmp_path / "template"
    shutil.copytree(TEMPLATE, template, ignore=shutil.ignore_patterns("__pycache__"))
    infra = template / "infra" / "dev.yaml"
    infra.write_text(infra.read_text().replace("replicas: 1", "replicas: 2"))
    assert build(template, DEFAULT_FILL, tmp_path / "r").package_hash != base
    agent = template / "agent" / "triage_agent" / "rai.py"
    shutil.copytree(TEMPLATE / "infra", template / "infra", dirs_exist_ok=True)
    agent.write_text(agent.read_text() + "\n# changed\n")
    assert build(template, DEFAULT_FILL, tmp_path / "r").package_hash != base


def test_invalid_fill_names_the_part_and_writes_nothing(tmp_path: Path) -> None:
    fill = tmp_path / "fill"
    shutil.copytree(DEFAULT_FILL, fill)
    (fill / "settings.yaml").write_text("token_budget: 1\nmodel_mode: simulated\nmodel_name: x\n")
    registry = tmp_path / "registry"
    with pytest.raises(BuildError, match="settings"):
        build(TEMPLATE, fill, registry)
    assert not registry.exists() or not any(registry.iterdir())


def test_manifest_and_extract(tmp_path: Path) -> None:
    built = build(TEMPLATE, DEFAULT_FILL, tmp_path / "r")
    manifest = json.loads(built.manifest.read_text())
    assert manifest["package_hash"] == built.package_hash
    assert manifest["template_id"] == "incident-triage"
    assert "fill/settings.yaml" in manifest["files"]
    assert "template/agent/triage_agent/app.py" in manifest["files"]
    assert not any("__pycache__" in f for f in manifest["files"])
    root = extract(tmp_path / "r", built.package_hash, tmp_path / "x")
    assert (root / "fill" / "routing_rules.yaml").is_file()
    with pytest.raises(BuildError, match="unknown package"):
        extract(tmp_path / "r", "sha256:" + "0" * 64, tmp_path / "y")
