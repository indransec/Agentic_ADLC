"""T032: `adlc-spec validate` per contracts/adlc-spec-cli.md."""

import json
from pathlib import Path

from typer.testing import CliRunner

from adlc.spec_toolkit.cli import app
from tests.support.spec_fixtures import build_bundle

runner = CliRunner()


def test_valid_bundle_exits_0(tmp_path: Path) -> None:
    root = build_bundle(tmp_path)
    result = runner.invoke(app, ["validate", str(root), "--no-baseline"])
    assert result.exit_code == 0, result.output
    assert "0 errors" in result.output


def test_errors_exit_1(tmp_path: Path) -> None:
    root = build_bundle(tmp_path, "V-06-unknown-scope")
    result = runner.invoke(app, ["validate", str(root), "--no-baseline"])
    assert result.exit_code == 1
    assert "V-06" in result.output


def test_missing_path_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", str(tmp_path / "nope")])
    assert result.exit_code == 2


def test_json_format(tmp_path: Path) -> None:
    root = build_bundle(tmp_path, "V-06-unknown-scope")
    result = runner.invoke(app, ["validate", str(root), "--no-baseline", "--format", "json"])
    data = json.loads(result.stdout)
    assert data["summary"]["errors"] >= 1
    assert {"rule_id", "level", "severity", "file", "path", "line", "column", "message"} <= set(
        data["findings"][0]
    )


def test_min_severity_hides_but_keeps_exit_code(tmp_path: Path) -> None:
    root = build_bundle(tmp_path, "V-06-unknown-scope")
    result = runner.invoke(app, ["validate", str(root), "--no-baseline", "--min-severity", "error"])
    assert result.exit_code == 1
    assert "V-23" not in result.output
    assert "V-06" in result.output
