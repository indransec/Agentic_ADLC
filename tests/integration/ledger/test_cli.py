"""T027: `adlc-ledger verify` (contracts/verification.md)."""

import json
from pathlib import Path

from sqlalchemy import create_engine, text
from typer.testing import CliRunner

from adlc.ledger.cli import app
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness
from tests.support.pg import patched_env

runner = CliRunner()


def _env(h: Harness, tmp_path: Path) -> dict[str, str]:
    return {**h.db.env, "ADLC_FILE_STORE_DIR": str(tmp_path / "files")}


def test_verified_exits_zero_with_the_report_shape(h: Harness, tmp_path: Path) -> None:
    usecase, _ = walk_to(h, "T3")
    with patched_env(_env(h, tmp_path)):
        result = runner.invoke(app, ["verify", "--usecase", usecase, "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report == {
        "scope": usecase,
        "records_checked": 3,
        "verified": True,
        "breaks": [],
        "unscoped": [],
    }
    actor = h.sql("SELECT actor FROM ledger.verification_run")[0][0]
    assert str(actor).startswith("cli:")


def test_breaks_exit_one(h: Harness, tmp_path: Path) -> None:
    usecase, _ = walk_to(h, "T2")
    superuser = create_engine(h.db.url("postgres", h.db.superuser_password))
    with superuser.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("UPDATE ledger.ledger_record SET content_json = '{}'::jsonb"))
    superuser.dispose()
    with patched_env(_env(h, tmp_path)):
        text_result = runner.invoke(app, ["verify", "--usecase", usecase])
        json_result = runner.invoke(app, ["verify", "--json"])
    assert text_result.exit_code == 1
    assert "2 breaks" in text_result.output and "content" in text_result.output
    report = json.loads(json_result.output)
    assert json_result.exit_code == 1 and report["scope"] == "all" and not report["verified"]
    assert set(report["breaks"][0]) == {"ledger_key", "check", "element", "expected", "actual"}


def test_configuration_error_exits_two(h: Harness, tmp_path: Path) -> None:
    with patched_env({**_env(h, tmp_path), "ADLC_ATTACHMENT_MAX": "lots"}):
        result = runner.invoke(app, ["verify"])
    assert result.exit_code == 2
