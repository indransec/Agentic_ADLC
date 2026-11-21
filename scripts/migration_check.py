"""``make migration-check``: fresh SQLite file, upgrade → downgrade → upgrade, then assert.

Run with ``uv run python -m scripts.migration_check`` from the repository root.
Exits 1 naming the failed step (FR-022).
"""

import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

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
# Feature 016: board engagement tables; the history ones are append-only.
BOARD_TABLES = {
    "board_link",
    "board_sync_state",
    "board_delivery",
    "board_requeue",
    "inbound_change",
    "inbound_outcome",
    "board_reconciliation",
}
BOARD_APPEND_ONLY = {"board_requeue", "inbound_change", "inbound_outcome", "board_reconciliation"}


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
    if missing := BOARD_TABLES - tables:
        raise AssertionError(f"board tables missing: {sorted(missing)}")
    updates = _names(
        db, "SELECT tbl_name FROM sqlite_master WHERE type = 'trigger' AND name LIKE '%_no_update'"
    )
    if unguarded := BOARD_APPEND_ONLY - (guarded & updates):
        raise AssertionError(f"board history tables not append-only: {sorted(unguarded)}")
    _assert_board_append_only(db)


def _assert_board_append_only(db: PlatformDatabase) -> None:
    """016: an UPDATE or DELETE on a board history row is refused for every connection."""
    engine = db.engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO inbound_change (work_item_id, update_id, rev, changer, kind) "
                    "VALUES (1, 1, 1, 'check', 'ignored')"
                )
            )
        for statement in (
            "UPDATE inbound_change SET kind = 'own' WHERE work_item_id = 1",
            "DELETE FROM inbound_change WHERE work_item_id = 1",
        ):
            try:
                with engine.begin() as conn:
                    conn.execute(text(statement))
            except DatabaseError:  # the trigger's refusal is the expected outcome
                continue
            raise AssertionError(f"inbound_change accepted: {statement}")
    finally:
        engine.dispose()


def main() -> int:
    steps: list[tuple[str, Callable[[PlatformDatabase], None]]] = [
        ("upgrade head", lambda db: alembic(db, "upgrade", "head")),
        ("downgrade base", lambda db: alembic(db, "downgrade", "base")),
        ("upgrade head (again)", lambda db: alembic(db, "upgrade", "head")),
        ("assert spec and board tables and triggers", _assert_final_state),
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
