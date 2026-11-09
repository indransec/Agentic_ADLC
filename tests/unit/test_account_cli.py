"""US4: `adlc-account hash` and `adlc-account check` (contracts/make-targets.md)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from adlc.cli import account
from adlc.identity.hashing import hash_password, verify_password

runner = CliRunner()
CATALOGUE = Path(__file__).resolve().parents[2] / "adlc-specs" / "shared" / "roles.yaml"


def _getpass(answers: list[str]) -> Iterator[str]:
    yield from answers


def test_hash_prints_only_the_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = _getpass(["my-password", "my-password"])
    monkeypatch.setattr(account, "getpass", lambda prompt="": next(answers))
    result = runner.invoke(account.app, ["hash"])
    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("scrypt$")
    assert verify_password("my-password", lines[0])
    assert "my-password" not in result.stdout


def test_hash_mismatch_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = _getpass(["one", "two"])
    monkeypatch.setattr(account, "getpass", lambda prompt="": next(answers))
    result = runner.invoke(account.app, ["hash"])
    assert result.exit_code == 1
    assert "scrypt$" not in result.stdout


def _env(monkeypatch: pytest.MonkeyPatch, accounts: Path, env: str = "dev") -> None:
    monkeypatch.setenv("ADLC_ENV", env)
    monkeypatch.setenv("ADLC_DB_HOST", "localhost")
    monkeypatch.setenv("ADLC_DB_APP_PASSWORD", "cli-app-password-0001")
    monkeypatch.setenv("ADLC_SESSION_SECRET", "cli-session-secret-" + "y" * 20)
    monkeypatch.setenv("ADLC_ACCOUNTS_FILE", str(accounts))
    monkeypatch.setenv("ADLC_ROLE_CATALOGUE", str(CATALOGUE))


def test_check_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    accounts = tmp_path / "a.yaml"
    accounts.write_text(
        "accounts:\n  - {account_name: coe.lead, display_name: C, roles: [adlc_coe], "
        f"credential_hash: '{hash_password('x')}'}}\n"
    )
    _env(monkeypatch, accounts, env="demo")
    result = runner.invoke(account.app, ["check"])
    assert result.exit_code == 0, result.output
    assert "OK, 1 account" in result.stdout


def test_check_reports_problem_by_account(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    accounts = tmp_path / "a.yaml"
    accounts.write_text(
        "accounts:\n  - {account_name: coe.lead, display_name: C, roles: [adlc_coe], "
        "credential_hash: REPLACE_WITH_HASH}\n"
    )
    _env(monkeypatch, accounts, env="demo")
    result = runner.invoke(account.app, ["check"])
    assert result.exit_code == 1
    assert "coe.lead" in result.output
