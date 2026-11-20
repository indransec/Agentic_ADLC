"""Operator commands and their exit codes (T015, T039)."""

from pathlib import Path

import pytest

from ado_sim.cli import INVALID, OK, REFUSED, run
from ado_sim.db import Database
from ado_sim.workitems import WorkItemStore
from tests.conftest import KEY, OWNER, SEED, title


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "data" / "sim.db"
    monkeypatch.setenv("ADO_SIM_DB_PATH", str(path))
    monkeypatch.setenv("ADO_SIM_TOKEN_KEY", KEY)
    monkeypatch.setenv("ADO_SIM_SEED_FILE", str(SEED))
    return path


def test_migrate_seed_and_tokens(env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["migrate"]) == OK
    assert run(["migrate"]) == OK
    assert "up to date" in capsys.readouterr().out
    assert run(["seed", "--file", str(SEED)]) == OK
    assert run(["seed", "--file", str(SEED)]) == REFUSED
    assert run(["seed", "--if-new", "--file", str(SEED)]) == OK
    capsys.readouterr()
    assert run(["token", "issue", OWNER, "--label", "laptop"]) == OK
    output = capsys.readouterr().out.splitlines()
    token = output[-1]
    assert len(token) == 52
    assert run(["token", "list"]) == OK
    listing = capsys.readouterr().out
    assert OWNER in listing and "laptop" in listing and token not in listing
    assert run(["token", "issue", "nobody@adlc.demo"]) == REFUSED
    assert run(["token", "revoke", "1"]) == OK
    assert run(["token", "revoke", "1"]) == REFUSED
    assert run(["token", "list", OWNER]) == OK
    assert "revoked" in capsys.readouterr().out


def test_settings_and_missing_database(
    env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(["token", "list"]) == INVALID
    assert "ado-sim migrate" in capsys.readouterr().err
    monkeypatch.setenv("ADO_SIM_TOKEN_KEY", "short")
    assert run(["migrate"]) == INVALID
    assert "ADO_SIM_TOKEN_KEY" in capsys.readouterr().err


def test_invalid_seed_file(env: Path, tmp_path: Path) -> None:
    assert run(["migrate"]) == OK
    broken = tmp_path / "broken.yaml"
    broken.write_text("organization: [", encoding="utf-8")
    assert run(["seed", "--file", str(broken)]) == INVALID


def test_reset(env: Path) -> None:
    assert run(["migrate"]) == OK
    assert run(["seed", "--file", str(SEED)]) == OK
    db = Database(env)
    store = WorkItemStore(db)
    with db.read() as conn:
        service = conn.execute("SELECT * FROM identity LIMIT 1").fetchone()
    from ado_sim.process import Identity

    who = Identity(service["id"], service["display_name"], service["unique_name"])
    store.create("Task", [title("before reset")], who)
    db.close()
    assert run(["reset"]) == REFUSED
    assert run(["reset", "--yes"]) == OK
    db = Database(env)
    with db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM work_item").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM revision").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM identity").fetchone()[0] > 0
    db.close()


def test_export_openapi(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "openapi.json"
    assert run(["export-openapi", "--check", "--output", str(output)]) == REFUSED
    assert run(["export-openapi", "--output", str(output)]) == OK
    assert run(["export-openapi", "--check", "--output", str(output)]) == OK
    assert '"openapi"' in output.read_text(encoding="utf-8")
