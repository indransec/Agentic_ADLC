"""016 T051: the adlc-board commands and their exit codes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from adlc.engagement import cli
from tests.support.api import write_accounts
from tests.support.db import PlatformDatabase

runner = CliRunner()


@pytest.fixture
def env(
    migrated_db: PlatformDatabase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, str]:
    values = {
        "ADLC_ENV": "dev",
        "ADLC_DB_PATH": str(migrated_db.path),
        "ADLC_ACCOUNTS_FILE": str(write_accounts(tmp_path / "accounts.yaml")),
        "ADLC_DEADLETTER_ROLE": "adlc_coe",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


def test_missing_settings_exit_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADLC_DB_PATH", raising=False)
    assert runner.invoke(cli.app, ["health"]).exit_code == 2


def test_health_with_the_board_disabled(env: dict[str, str]) -> None:
    result = runner.invoke(cli.app, ["health"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["enabled"] is False


@pytest.mark.parametrize("args", [["check-mapping"], ["reconcile", "--as", "adlc_coe-person"]])
def test_board_commands_need_the_board_enabled(env: dict[str, str], args: list[str]) -> None:
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 2
    assert "ADLC_BOARD_ENABLED" in result.output


def test_requeue_needs_the_coe_role(env: dict[str, str]) -> None:
    result = runner.invoke(cli.app, ["requeue", "UC-0001", "--as", "product_owner-person"])
    assert result.exit_code == 1 and "adlc_coe" in result.output


def test_an_unknown_account(env: dict[str, str]) -> None:
    result = runner.invoke(cli.app, ["requeue", "UC-0001", "--as", "nobody"])
    assert result.exit_code == 1
