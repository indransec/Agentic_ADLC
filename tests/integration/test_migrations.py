"""US2: versioned migrations over the platform data store (FR-006 to FR-009, SC-003)."""

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import text

from tests.support.db import ALEMBIC_INI, REPO_ROOT, PlatformDatabase, alembic

# One table from each former data area (spec, run, ledger, events, tools)
AREAS = {"spec_registry", "terminal_run", "ledger_record", "outbox_event", "tool_call"}


def _head() -> str:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(REPO_ROOT / "db" / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


def _tables(db: PlatformDatabase) -> set[str]:
    engine = db.engine()
    try:
        with engine.connect() as conn:
            return set(
                conn.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
                        "AND name NOT LIKE 'sqlite_%'"
                    )
                ).scalars()
            )
    finally:
        engine.dispose()


def _version(db: PlatformDatabase) -> str | None:
    if "alembic_version" not in _tables(db):
        return None
    engine = db.engine()
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()


def test_upgrade_creates_every_data_area(migrated_db: PlatformDatabase) -> None:
    assert _tables(migrated_db) >= AREAS
    assert _version(migrated_db) == _head()


def test_upgrade_again_is_noop(migrated_db: PlatformDatabase) -> None:
    before = _tables(migrated_db)
    alembic(migrated_db, "upgrade", "head")
    assert _version(migrated_db) == _head()
    assert _tables(migrated_db) == before


def test_downgrade_base_removes_everything(platform_db: PlatformDatabase) -> None:
    alembic(platform_db, "upgrade", "head")
    alembic(platform_db, "downgrade", "base")
    assert _tables(platform_db) == {"alembic_version"}


def test_round_trip_ten_times(platform_db: PlatformDatabase) -> None:
    for _ in range(10):
        alembic(platform_db, "upgrade", "head")
        alembic(platform_db, "downgrade", "base")
    assert _tables(platform_db) == {"alembic_version"}


def test_unknown_revision_in_store_is_reported(platform_db: PlatformDatabase) -> None:
    alembic(platform_db, "upgrade", "head")
    engine = platform_db.engine()
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = '9999'"))
        with pytest.raises(CommandError, match="9999"):
            alembic(platform_db, "upgrade", "head")
    finally:
        engine.dispose()
