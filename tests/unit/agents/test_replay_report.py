"""T028: the replay report, the baseline comparison and the command's exit codes
(contracts/replay.md; FR-019, FR-020)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from adlc.agents.replay import (
    Report,
    TerminalResult,
    UseCaseResult,
    app,
    load_references,
    write_report,
)

ROOT = Path(__file__).resolve().parents[3]


def terminal(tid: str, recommendation: str = "pass", **over: object) -> TerminalResult:
    values: dict[str, object] = {
        "terminal_id": tid,
        "run_id": f"UC-0001/{tid}/run-1",
        "state": "awaiting_sign_off",
        "mandatory_missing": [],
        "blocking_failed": [],
        "first_attempt_clean": True,
        "recommendation": recommendation,
        "reason": "ok",
        "root_cause": None,
        "clarifications": 0,
        "citations": 1,
        "steps": 3,
        "tokens_in": 100,
        "tokens_out": 50,
        "cost_usd": 0.001,
        "agent": "a",
        "agent_version": "1.1.0",
        "prompt_hash": "sha256:x",
        "playbook_hashes": {"PB": "sha256:y"},
        "models": ["openai/gpt-4o-mini"],
    }
    values.update(over)
    return TerminalResult(**values)  # type: ignore[arg-type]


def test_references_load() -> None:
    refs = load_references(ROOT / "data" / "reference_usecases")
    assert {r.id for r in refs} == {"travel-claims", "it-service-desk", "loan-prescreening"}
    assert {r.expected["risk_tier"] for r in refs} == {"low", "medium", "high"}
    assert all(len(r.intake_text) >= 200 and r.until for r in refs)
    assert [
        r.id for r in load_references(ROOT / "data" / "reference_usecases", ["it-service-desk"])
    ] == ["it-service-desk"]


def test_report_files_and_ok(tmp_path: Path) -> None:
    good = UseCaseResult(
        "travel-claims", "UC-0001", "completed", "medium", [terminal("T0"), terminal("T1")]
    )
    folder = write_report(Report("recording", "dev", [good]), tmp_path)
    data = json.loads((folder / "report.json").read_text())
    assert data["ok"] is True and data["usecases"][0]["terminals"][0]["citations"] == 1
    assert "| T0 |" in (folder / "report.md").read_text()
    missing = UseCaseResult(
        "x", "UC-0002", "completed", "low", [terminal("T0", mandatory_missing=["raci"])]
    )
    assert not Report("live", "dev", [missing]).ok
    stopped = UseCaseResult("y", "UC-0003", "unanswered clarification", "low", [])
    assert not Report("live", "dev", [stopped]).ok


def test_baseline_marks_changed_recommendations(tmp_path: Path) -> None:
    first = write_report(
        Report(
            "recording",
            None,
            [UseCaseResult("u", "UC-1", "completed", None, [terminal("T0"), terminal("T1")])],
        ),
        tmp_path / "a",
    )
    second = Report(
        "live",
        "dev",
        [UseCaseResult("u", "UC-9", "completed", None, [terminal("T0"), terminal("T1", "rework")])],
    )
    folder = write_report(second, tmp_path / "b", baseline=first)
    data = json.loads((folder / "report.json").read_text())
    changed = {t["terminal_id"]: t["changed_from"] for t in data["usecases"][0]["terminals"]}
    assert changed == {"T0": None, "T1": "pass"}


def test_configuration_errors_exit_2() -> None:
    runner = CliRunner()
    assert runner.invoke(app, []).exit_code == 2  # neither --profile nor --recording
    assert runner.invoke(app, ["--profile", "dev", "--recording", "x"]).exit_code == 2
    assert runner.invoke(app, ["--record", "x", "--recording", "y"]).exit_code == 2
