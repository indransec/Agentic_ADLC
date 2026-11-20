"""SC-006: seeding and resetting from seed/demo.yaml each take under a minute (T047)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from ado_sim.cli import OK, run
from tests.conftest import KEY, SEED

LIMIT_SECONDS = 60.0


def test_seed_and_reset_under_a_minute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, measurements: dict[str, str]
) -> None:
    monkeypatch.setenv("ADO_SIM_DB_PATH", str(tmp_path / "sim.db"))
    monkeypatch.setenv("ADO_SIM_TOKEN_KEY", KEY)
    monkeypatch.setenv("ADO_SIM_SEED_FILE", str(SEED))
    assert run(["migrate"]) == OK
    started = time.perf_counter()
    assert run(["seed", "--file", str(SEED)]) == OK
    seeded = time.perf_counter() - started
    started = time.perf_counter()
    assert run(["reset", "--yes"]) == OK
    reset = time.perf_counter() - started
    measurements["SC-006 seed / reset"] = f"{seeded:.2f} s / {reset:.2f} s"
    assert seeded < LIMIT_SECONDS and reset < LIMIT_SECONDS
