"""T056: registration is transactional, idempotent, version-checked and serialised (US4)."""

import shutil
import threading
import time
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from sqlalchemy import Engine, text

from adlc.spec_toolkit import register as register_module
from adlc.spec_toolkit.register import RegistrationRefused, register
from tests.support.pg import PlatformDatabase

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def specs(tmp_path: Path) -> Path:
    target = tmp_path / "adlc-specs"
    shutil.copytree(ROOT / "adlc-specs", target)
    return target


def _edit(path: Path, pointer: str, value: object) -> None:
    yaml = YAML()
    data = yaml.load(path.read_text())
    node = data
    keys = pointer.strip("/").split("/")
    for key in keys[:-1]:
        node = node[int(key)] if isinstance(node, list) else node[key]
    if isinstance(node, list):
        node[int(keys[-1])] = value
    else:
        node[keys[-1]] = value
    with path.open("w") as handle:
        yaml.dump(data, handle)


def _count(engine: Engine, sql: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(sql)).scalar_one())


def test_first_registration_creates_everything(owner_engine: Engine, specs: Path) -> None:
    started = time.monotonic()
    report = register(specs, owner_engine)
    assert time.monotonic() - started < 30  # SC-005
    assert report.registered_count == 10 + 14 + 31
    assert (
        _count(owner_engine, "SELECT count(*) FROM spec.spec_registry WHERE status='active'") == 10
    )
    assert (
        _count(owner_engine, "SELECT count(*) FROM spec.spec_catalogue WHERE status='active'") == 14
    )
    assert _count(owner_engine, "SELECT count(*) FROM spec.playbook_registry") == 31
    assert _count(owner_engine, "SELECT count(*) FROM spec.spec_timeline") == 30
    assert _count(owner_engine, "SELECT count(*) FROM spec.spec_event_route") == 7


def test_second_registration_writes_nothing(owner_engine: Engine, specs: Path) -> None:
    register(specs, owner_engine)
    report = register(specs, owner_engine)
    assert report.registered_count == 0
    assert report.unchanged_count == 55


def test_changed_content_same_version_refused(owner_engine: Engine, specs: Path) -> None:
    register(specs, owner_engine)
    _edit(specs / "terminals" / "T0.yaml", "/terminal/timeline/reminder_after", "3d")
    with pytest.raises(RegistrationRefused, match="T0"):
        register(specs, owner_engine)
    assert _count(owner_engine, "SELECT count(*) FROM spec.spec_registry") == 10


def test_bump_registers_and_deprecates(owner_engine: Engine, specs: Path) -> None:
    register(specs, owner_engine)
    path = specs / "terminals" / "T0.yaml"
    _edit(path, "/terminal/metadata/purpose", "Should we do this at all? (reworded)")
    _edit(path, "/terminal/metadata/version", "1.0.1")
    report = register(specs, owner_engine)
    assert report.registered_count == 1
    with owner_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT version, status, deprecated_at IS NOT NULL FROM spec.spec_registry "
                "WHERE terminal_id='T0' ORDER BY version"
            )
        ).all()
    assert [tuple(r) for r in rows] == [("1.0.0", "deprecated", True), ("1.0.1", "active", False)]


def test_insufficient_bump_refused(owner_engine: Engine, specs: Path) -> None:
    register(specs, owner_engine)
    path = specs / "terminals" / "T0.yaml"
    _edit(path, "/terminal/outcome_model/pass/route", "lifecycle_closed")
    _edit(path, "/terminal/metadata/version", "1.0.1")
    with pytest.raises(RegistrationRefused, match="major"):
        register(specs, owner_engine)


def test_playbook_changed_same_version_refused(owner_engine: Engine, specs: Path) -> None:
    register(specs, owner_engine)
    playbook = specs / "playbooks" / "t0-intake.md"
    playbook.write_text(playbook.read_text() + "\nMore text.\n")
    with pytest.raises(RegistrationRefused, match="PB-T0-01"):
        register(specs, owner_engine)


def test_validation_errors_refused_before_writing(owner_engine: Engine, specs: Path) -> None:
    _edit(
        specs / "terminals" / "T3.yaml",
        "/terminal/authorities/tool_scopes/0",
        "mcp:gitt:branch_write",
    )
    with pytest.raises(RegistrationRefused, match="V-06"):
        register(specs, owner_engine)
    assert _count(owner_engine, "SELECT count(*) FROM spec.spec_registry") == 0


def test_dry_run_leaves_nothing(owner_engine: Engine, specs: Path) -> None:
    report = register(specs, owner_engine, dry_run=True)
    assert report.registered_count == 55
    assert _count(owner_engine, "SELECT count(*) FROM spec.spec_registry") == 0


def test_interrupted_registration_leaves_nothing(
    owner_engine: Engine, specs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = register_module._insert_projection

    def explode(*args: object, **kwargs: object) -> None:
        original(*args, **kwargs)  # type: ignore[arg-type]
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(register_module, "_insert_projection", explode)
    with pytest.raises(RuntimeError):
        register(specs, owner_engine)
    assert _count(owner_engine, "SELECT count(*) FROM spec.spec_registry") == 0
    assert _count(owner_engine, "SELECT count(*) FROM spec.spec_trigger") == 0


def test_concurrent_registrations_serialise(
    migrated_db: PlatformDatabase, owner_engine: Engine, specs: Path
) -> None:
    results: list[int] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            results.append(register(specs, owner_engine).registered_count)
        except BaseException as exc:  # noqa: BLE001 - surface any thread failure
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert sorted(results) == [0, 55]
    assert (
        _count(owner_engine, "SELECT count(*) FROM spec.spec_registry WHERE status='active'") == 10
    )
