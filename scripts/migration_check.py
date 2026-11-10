"""``make migration-check``: fresh PostgreSQL, upgrade → downgrade → upgrade, then assert.

Run with ``uv run python -m scripts.migration_check`` from the repository root.
Exits 1 naming the failed step (FR-022).
"""

import sys
from collections.abc import Callable

from sqlalchemy import create_engine, text

from tests.support.pg import PlatformDatabase, alembic, platform_postgres

SCHEMAS = {"spec", "run", "ledger", "events"}
TRIGGERS = {"ledger_record_no_update_delete", "ledger_record_no_truncate"}
# Feature 002: spec registry tables, each guarded by at least one no-truncate trigger
# (usecase_spec_pin is written by 003 and has no guard yet).
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
}
GUARDED_SPEC_TABLES = SPEC_TABLES - {"usecase_spec_pin"}


def _assert_final_state(db: PlatformDatabase) -> None:
    engine = create_engine(db.owner_url)
    try:
        with engine.connect() as conn:
            schemas = set(
                conn.execute(
                    text("SELECT nspname FROM pg_namespace WHERE nspname = ANY(:n)"),
                    {"n": list(SCHEMAS)},
                ).scalars()
            )
            triggers = set(
                conn.execute(
                    text(
                        "SELECT tgname FROM pg_trigger "
                        "WHERE tgrelid = 'ledger.ledger_record'::regclass AND NOT tgisinternal"
                    )
                ).scalars()
            )
            spec_tables = set(
                conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'spec'")
                ).scalars()
            )
            guarded = set(
                conn.execute(
                    text(
                        "SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'spec' AND t.tgname LIKE '%_no_truncate'"
                    )
                ).scalars()
            )
    finally:
        engine.dispose()
    if spec_tables != SPEC_TABLES:
        raise AssertionError(f"spec tables differ: missing {sorted(SPEC_TABLES - spec_tables)}")
    if guarded != GUARDED_SPEC_TABLES:
        raise AssertionError(f"spec tables without guard: {sorted(GUARDED_SPEC_TABLES - guarded)}")
    if schemas != SCHEMAS:
        raise AssertionError(f"schemas missing: {sorted(SCHEMAS - schemas)}")
    if triggers != TRIGGERS:
        raise AssertionError(f"ledger triggers missing: {sorted(TRIGGERS - triggers)}")


def main() -> int:
    steps: list[tuple[str, Callable[[PlatformDatabase], None]]] = [
        ("upgrade head", lambda db: alembic(db, "upgrade", "head")),
        ("downgrade base", lambda db: alembic(db, "downgrade", "base")),
        ("upgrade head (again)", lambda db: alembic(db, "upgrade", "head")),
        ("assert schemas, spec tables and triggers", _assert_final_state),
    ]
    with platform_postgres() as db:
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
