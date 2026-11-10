"""T007/T009: prompts and the two agent catalogues are registered with the specs (feature 006)."""

import shutil
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from adlc.spec_toolkit.register import RegistrationRefused, register

SPECS = Path(__file__).resolve().parents[3] / "adlc-specs"


def _copy(tmp_path: Path) -> Path:
    root = tmp_path / "adlc-specs"
    shutil.copytree(SPECS, root)
    return root


def test_prompts_and_catalogues_register(owner_engine: Engine, tmp_path: Path) -> None:
    root = _copy(tmp_path)
    report = register(root, owner_engine)
    kinds = {(i.kind, i.name) for i in report.items}
    assert ("prompt", "common-terminal-reviewer") in kinds
    assert ("catalogue", "model_catalogue") in kinds and ("catalogue", "agents") in kinds
    with owner_engine.connect() as conn:
        row = conn.execute(
            text("SELECT version, path, content_hash FROM spec.prompt_registry")
        ).one()
    assert row[0] == "1.0.0" and row[1] == "prompts/common-terminal-reviewer.md"
    assert row[2].startswith("sha256:")
    again = register(root, owner_engine)
    assert [i.action for i in again.items if i.kind == "prompt"] == ["unchanged"]


def test_changed_prompt_needs_a_new_version(owner_engine: Engine, tmp_path: Path) -> None:
    root = _copy(tmp_path)
    register(root, owner_engine)
    prompt = root / "prompts" / "common-terminal-reviewer.md"
    prompt.write_text(prompt.read_text() + "\nOne more rule.\n")
    with pytest.raises(RegistrationRefused, match="prompt changed"):
        register(root, owner_engine)
