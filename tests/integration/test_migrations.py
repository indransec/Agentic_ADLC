"""US2: versioned migrations over the four owned data areas (FR-006 to FR-009, SC-003)."""

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import create_engine, text

from tests.support.pg import ALEMBIC_INI, REPO_ROOT, PlatformDatabase, alembic

SCHEMAS = {"spec", "run", "ledger", "events"}


def _head() -> str:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(REPO_ROOT / "db" / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


def _schemas_and_owners(db: PlatformDatabase) -> dict[str, str]:
    engine = create_engine(db.owner_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT nspname, pg_get_userbyid(nspowner) FROM pg_namespace "
                    "WHERE nspname = ANY(:names)"
                ),
                {"names": list(SCHEMAS)},
            )
            return {name: owner for name, owner in rows}
    finally:
        engine.dispose()


def _version(db: PlatformDatabase) -> str | None:
    engine = create_engine(db.owner_url)
    try:
        with engine.connect() as conn:
            exists = conn.execute(text("SELECT to_regclass('public.alembic_version')")).scalar()
            if exists is None:
                return None
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()


def _ledger_table_exists(db: PlatformDatabase) -> bool:
    engine = create_engine(db.owner_url)
    try:
        with engine.connect() as conn:
            return (
                conn.execute(text("SELECT to_regclass('ledger.ledger_record')")).scalar()
                is not None
            )
    finally:
        engine.dispose()


def test_upgrade_creates_four_owned_schemas(migrated_db: PlatformDatabase) -> None:
    owners = _schemas_and_owners(migrated_db)
    assert owners == {name: migrated_db.owner_user for name in SCHEMAS}
    assert _ledger_table_exists(migrated_db)
    assert _version(migrated_db) == _head()


def test_upgrade_again_is_noop(migrated_db: PlatformDatabase) -> None:
    alembic(migrated_db, "upgrade", "head")
    assert _version(migrated_db) == _head()
    assert set(_schemas_and_owners(migrated_db)) == SCHEMAS


def test_downgrade_base_removes_everything(platform_db: PlatformDatabase) -> None:
    alembic(platform_db, "upgrade", "head")
    alembic(platform_db, "downgrade", "base")
    assert _schemas_and_owners(platform_db) == {}
    assert not _ledger_table_exists(platform_db)


def test_round_trip_ten_times(platform_db: PlatformDatabase) -> None:
    for _ in range(10):
        alembic(platform_db, "upgrade", "head")
        alembic(platform_db, "downgrade", "base")
    assert _schemas_and_owners(platform_db) == {}


def test_unknown_revision_in_store_is_reported(platform_db: PlatformDatabase) -> None:
    alembic(platform_db, "upgrade", "head")
    engine = create_engine(platform_db.owner_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = '9999'"))
        with pytest.raises(CommandError, match="9999"):
            alembic(platform_db, "upgrade", "head")
        with engine.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = :v"), {"v": _head()})
    finally:
        engine.dispose()
        alembic(platform_db, "downgrade", "base")
