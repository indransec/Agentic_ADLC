"""US5: developers and CI share one command list (FR-022, FR-023)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAKE_TARGETS = {
    "install",
    "up",
    "down",
    "status",
    "reset",
    "migrate",
    "migrate-down",
    "lint",
    "typecheck",
    "test",
    "migration-check",
    "secret-scan",
    "check",
}
SETUP_ONLY_RUNS = {"make install"}


def _make_targets() -> set[str]:
    text = (ROOT / "Makefile").read_text()
    return set(re.findall(r"^([a-z][a-z-]*):", text, flags=re.MULTILINE))


def _workflow_runs() -> list[str]:
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    return [line.strip() for line in re.findall(r"run:\s*(.+)", text)]


def test_makefile_defines_every_contract_target() -> None:
    assert _make_targets() >= MAKE_TARGETS


def test_ci_runs_only_make_check() -> None:
    runs = _workflow_runs()
    checks = [run for run in runs if run not in SETUP_ONLY_RUNS]
    assert checks == ["make check"]
    for run in runs:
        assert run.startswith("make "), run


def test_check_runs_all_steps_in_order() -> None:
    text = (ROOT / "Makefile").read_text()
    match = re.search(r"^check:[^\n]*\n((?:\t[^\n]*\n)+)", text, flags=re.MULTILINE)
    assert match is not None
    body = match.group(1)
    positions = [
        body.find(step) for step in ("lint", "typecheck", "test", "migration-check", "secret-scan")
    ]
    assert all(p >= 0 for p in positions)
    assert positions == sorted(positions)
