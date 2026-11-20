"""Seed file validation and loading (T009, written before ado_sim.seed)."""

from pathlib import Path

import pytest

from ado_sim.db import Database, migrate
from ado_sim.seed import SeedError, is_seeded, load_seed, read_seed

VALID = """\
organization: test-org
project: Test Project
areas:
  - Team A
  - Team A\\Sub
process:
  agile_states:
    - {name: New, category: Proposed}
    - {name: Active, category: InProgress}
    - {name: Closed, category: Completed}
  types:
    Epic:
      states:
        - {name: Stage One, category: Proposed}
        - {name: Stage Two, category: InProgress}
        - {name: Done, category: Completed}
      fields: [Custom.Stage]
    Task:
      states: agile
      fields: [{ref: Custom.Choice, allowed_values: [Yes, No]}]
  custom_fields:
    Custom.Stage: {type: string}
    Custom.Choice: {type: string, name: Choice}
identities:
  - {unique_name: svc@test, display_name: Service}
  - {unique_name: user@test, display_name: User}
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "seed.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "s.db", create=True)
    migrate(database)
    return database


def test_valid_file_loads_everything(tmp_path: Path, db: Database) -> None:
    assert not is_seeded(db)
    load_seed(db, _write(tmp_path, VALID))
    assert is_seeded(db)
    with db.read() as conn:
        assert conn.execute("SELECT name FROM organization").fetchone()[0] == "test-org"
        assert conn.execute("SELECT name FROM project").fetchone()[0] == "Test Project"
        paths = [r[0] for r in conn.execute("SELECT path FROM area_node ORDER BY id")]
        assert paths == ["Test Project", "Test Project\\Team A", "Test Project\\Team A\\Sub"]
        states = [
            (r[0], r[1])
            for r in conn.execute(
                "SELECT name, category FROM work_item_type_state WHERE type_name = 'Epic'"
                " ORDER BY ordinal"
            )
        ]
        assert states == [
            ("Stage One", "Proposed"),
            ("Stage Two", "InProgress"),
            ("Done", "Completed"),
        ]
        task_states = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM work_item_type_state WHERE type_name = 'Task' ORDER BY ordinal"
            )
        ]
        assert task_states == ["New", "Active", "Closed"]
        assert (
            conn.execute(
                "SELECT type FROM field WHERE reference_name = 'Custom.Choice'"
            ).fetchone()[0]
            == "string"
        )
        epic_fields = {
            r[0]
            for r in conn.execute(
                "SELECT reference_name FROM work_item_type_field WHERE type_name = 'Epic'"
            )
        }
        assert {"Custom.Stage", "System.Title", "System.State"} <= epic_fields
        assert "Custom.Choice" not in epic_fields
        allowed = conn.execute(
            "SELECT allowed_values FROM work_item_type_field"
            " WHERE type_name = 'Task' AND reference_name = 'Custom.Choice'"
        ).fetchone()[0]
        assert allowed == '["Yes", "No"]'
        names = [
            r[0] for r in conn.execute("SELECT unique_name FROM identity ORDER BY unique_name")
        ]
        assert names == ["svc@test", "user@test"]
        assert conn.execute("SELECT COUNT(*) FROM access_token").fetchone()[0] == 0
    db.close()


def test_ids_are_deterministic(tmp_path: Path) -> None:
    first = read_seed(_write(tmp_path, VALID))
    second = read_seed(_write(tmp_path, VALID))
    assert first.identities == second.identities
    assert first.organization_id == second.organization_id


def test_seeding_twice_is_refused(tmp_path: Path, db: Database) -> None:
    path = _write(tmp_path, VALID)
    load_seed(db, path)
    with pytest.raises(SeedError, match="already seeded"):
        load_seed(db, path)
    db.close()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("Custom.Stage: {type: string}", "Custom.Stage: {type: blob}"), "type"),
        (
            (
                "    Task:\n      states: agile\n",
                "    Task:\n      states: []\n",
            ),
            "states",
        ),
        (
            (
                "  - {unique_name: user@test, display_name: User}",
                "  - {unique_name: SVC@test, display_name: User}",
            ),
            "duplicate",
        ),
        (("  - Team A\\Sub", "  - \\Other\\Area"), "area"),
        (("{name: Done, category: Completed}", "{name: Done, category: Finished}"), "category"),
        (
            (
                "  - {unique_name: svc@test, display_name: Service}",
                "  - {unique_name: svc@test, display_name: Service, token: abc}",
            ),
            "token",
        ),
        (("fields: [Custom.Stage]", "fields: [Custom.Missing]"), "Custom.Missing"),
        (("organization: test-org", "organisation: test-org"), "organisation"),
        (("Custom.Stage: {type: string}", "System.Title: {type: string}"), "System.Title"),
    ],
)
def test_refusals(tmp_path: Path, db: Database, change: tuple[str, str], message: str) -> None:
    old, new = change
    assert old in VALID
    with pytest.raises(SeedError, match=message):
        load_seed(db, _write(tmp_path, VALID.replace(old, new)))
    assert not is_seeded(db)
    db.close()


def test_secret_like_keys_anywhere(tmp_path: Path) -> None:
    text = VALID.replace("organization: test-org", "organization: test-org\nclient_secret: x")
    with pytest.raises(SeedError, match="client_secret"):
        read_seed(_write(tmp_path, text))


def test_not_yaml(tmp_path: Path) -> None:
    with pytest.raises(SeedError):
        read_seed(_write(tmp_path, "organization: [unclosed"))
    with pytest.raises(SeedError):
        read_seed(tmp_path / "missing.yaml")


def test_demo_seed_is_valid() -> None:
    seed = read_seed(Path(__file__).resolve().parents[2] / "seed" / "demo.yaml")
    assert seed.project
    assert any(i.unique_name.startswith("adlc-platform@") for i in seed.identities)
