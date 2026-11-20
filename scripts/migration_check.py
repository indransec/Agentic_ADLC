"""``make migration-check``: fresh SQLite file, upgrade → downgrade → upgrade, then assert.

Run with ``uv run python -m scripts.migration_check`` from the repository root.
Exits 1 naming the failed step (FR-022).
"""

import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import text

from tests.support.db import PlatformDatabase, alembic

LEDGER_TRIGGERS = {"ledger_record_no_update", "ledger_record_no_delete"}
# Feature 002: spec registry tables, each refusing deletes (usecase_spec_pin is written by 003
# and has no guard).
SPEC_TABLES = {
    "spec_registry",
    "spec_catalogue",
    "playbook_registry",
    "spec_trigger",
    "spec_outcome_route",
    "spec_event_route",
    "spec_change_class",
    "spec_timeline",
    "usecase_spec_pin",
    "prompt_registry",  # feature 006
}
GUARDED_SPEC_TABLES = SPEC_TABLES - {"usecase_spec_pin"}


def _names(db: PlatformDatabase, sql: str) -> set[str]:
    engine = db.engine()
    try:
        with engine.connect() as conn:
            return {str(n) for n in conn.execute(text(sql)).scalars()}
    finally:
        engine.dispose()


def _assert_final_state(db: PlatformDatabase) -> None:
    tables = _names(db, "SELECT name FROM sqlite_master WHERE type = 'table'")
    triggers = _names(
        db, "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'ledger_record'"
    )
    guarded = _names(
        db, "SELECT tbl_name FROM sqlite_master WHERE type = 'trigger' AND name LIKE '%_no_delete'"
    )
    if missing := SPEC_TABLES - tables:
        raise AssertionError(f"spec tables missing: {sorted(missing)}")
    if unguarded := GUARDED_SPEC_TABLES - guarded:
        raise AssertionError(f"spec tables without guard: {sorted(unguarded)}")
    if triggers != LEDGER_TRIGGERS:
        raise AssertionError(f"ledger triggers missing: {sorted(LEDGER_TRIGGERS - triggers)}")


def main() -> int:
    steps: list[tuple[str, Callable[[PlatformDatabase], None]]] = [
        ("upgrade head", lambda db: alembic(db, "upgrade", "head")),
        ("downgrade base", lambda db: alembic(db, "downgrade", "base")),
        ("upgrade head (again)", lambda db: alembic(db, "upgrade", "head")),
        ("assert spec tables and triggers", _assert_final_state),
    ]
    with tempfile.TemporaryDirectory() as folder:
        db = PlatformDatabase(Path(folder) / "adlc.db")
        for name, step in steps:
            try:
                step(db)
            except Exception as exc:  # report any failure by step name
                print(
                    f"migration-check FAILED at '{name}': {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
                return 1
            print(f"migration-check: {name} ok")
    print("migration-check: passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
