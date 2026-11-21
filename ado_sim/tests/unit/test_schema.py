import sqlite3
from pathlib import Path

import pytest

from ado_sim.db import Database, migrate


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "s.db", create=True)
    migrate(database)
    with database.write() as conn:
        conn.execute(
            "INSERT INTO identity (id, display_name, unique_name) VALUES ('i', 'I', 'i@x')"
        )
        conn.execute(
            "INSERT INTO work_item_type (name, reference_name, ordinal) VALUES ('Task', 'T', 0)"
        )
        conn.execute(
            "INSERT INTO work_item (type_name, rev, fields, changed_date, state, area_path)"
            " VALUES ('Task', 1, '{}', 't', 'New', 'P')"
        )
        conn.execute(
            "INSERT INTO revision (work_item_id, rev, fields, relations) VALUES (1, 1, '{}', '[]')"
        )
        conn.execute(
            "INSERT INTO work_item_update (work_item_id, id, rev, revision_bearing, revised_by,"
            " change_date, fields, relations) VALUES (1, 1, 1, 1, 'i', 't', '{}', '{}')"
        )
    return database


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE revision SET fields = '{\"x\": 1}'",
        "DELETE FROM revision",
        "UPDATE work_item_update SET fields = '{}'",
        "DELETE FROM work_item_update",
    ],
)
def test_history_is_append_only(db: Database, statement: str) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), db.write() as conn:
        conn.execute(statement)
    db.close()


def test_state_category_is_checked(db: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError), db.write() as conn:
        conn.execute(
            "INSERT INTO work_item_type_state (type_name, name, category, ordinal)"
            " VALUES ('Task', 'Odd', 'Elsewhere', 0)"
        )
    db.close()


def test_pages_schema(db: Database) -> None:
    """017 T005: page passwords, sessions, board settings and the service flag."""
    from ado_sim.db import LATEST_VERSION, schema_version

    assert schema_version(db) == LATEST_VERSION >= 2
    with db.read() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        columns = {r[1] for r in conn.execute("PRAGMA table_info(identity)")}
    assert {"page_password", "page_session", "board_setting"} <= tables
    assert "is_service" in columns
