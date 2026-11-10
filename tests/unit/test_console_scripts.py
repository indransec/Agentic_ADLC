"""Every console script resolves to something that runs a command (005: `adlc-ledger` once
pointed at a Typer callback, which exits 0 without doing anything)."""

import importlib
import tomllib
from pathlib import Path

import pytest
import typer

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
SCRIPTS = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["scripts"]


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_script_target_is_runnable(name: str) -> None:
    module, _, attribute = SCRIPTS[name].partition(":")
    target = getattr(importlib.import_module(module), attribute)
    if isinstance(target, typer.Typer):
        return
    assert callable(target)
    # A plain function must not be a Typer app's callback (that only sets up subcommands).
    for value in vars(importlib.import_module(module)).values():
        if isinstance(value, typer.Typer) and value.registered_callback is not None:
            assert value.registered_callback.callback is not target, (
                f"{name} points at the callback of a Typer app; point it at the app"
            )
