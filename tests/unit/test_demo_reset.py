"""014 T009a (FR-004; analysis A1): the demo reset and the resilience checks run only in the demo
environment; the guard comes before the confirmation and before anything is removed."""

import os
import subprocess

import pytest

from tests.support.pg import REPO_ROOT

GUARD = REPO_ROOT / "deploy" / "require-env.sh"


def run_guard(env: str | None, *allowed: str) -> int:
    environment = {k: v for k, v in os.environ.items() if k != "ADLC_ENV"}
    if env is not None:
        environment["ADLC_ENV"] = env
    return subprocess.run(
        ["bash", str(GUARD), *allowed], env=environment, capture_output=True
    ).returncode  # noqa: S603, S607


@pytest.mark.parametrize(("env", "code"), [("demo", 0), ("dev", 1), (None, 1), ("production", 1)])
def test_guard(env: str | None, code: int) -> None:
    assert run_guard(env, "demo") == code


def _recipe(target: str) -> list[str]:
    lines = (REPO_ROOT / "Makefile").read_text().splitlines()
    start = lines.index(f"{target}: .env") + 1
    recipe = []
    for line in lines[start:]:
        if not line.startswith("\t"):
            break
        recipe.append(line.strip())
    return recipe


def test_reset_guards_then_confirms_then_removes() -> None:
    recipe = _recipe("demo-reset")
    guard = next(i for i, line in enumerate(recipe) if "require-env.sh demo" in line)
    confirm = next(i for i, line in enumerate(recipe) if "confirm-env.sh" in line)
    remove = next(i for i, line in enumerate(recipe) if "down -v" in line)
    assert guard < confirm < remove


def test_resilience_is_demo_only() -> None:
    assert any("require-env.sh demo" in line for line in _recipe("resilience"))
