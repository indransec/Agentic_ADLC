"""T054: the spec schema is append-only except permitted status transitions (FR-021, FR-022)."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

HASH = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64

PROJECTIONS = (
    "spec_trigger",
    "spec_outcome_route",
    "spec_event_route",
    "spec_change_class",
    "spec_timeline",
)


def _insert_registry(
    conn: Connection,
    terminal: str = "T0",
    version: str = "1.0.0",
    status: str = "active",
    content_hash: str = HASH,
) -> int:
    return int(
        conn.execute(
            text(
                "INSERT INTO spec.spec_registry (terminal_id, version, status, schema_version, "
                "spec_yaml, spec_json, content_hash, trigger_events, emitted_events) "
                "VALUES (:t, :v, :s, '1.1.0', 'x', '{}'::jsonb, :h, ARRAY['a.b'], ARRAY['c.d']) "
                "RETURNING spec_registry_id"
            ),
            {"t": terminal, "v": version, "s": status, "h": content_hash},
        ).scalar_one()
    )


@pytest.fixture
def seeded(owner_engine: Engine) -> Iterator[int]:
    with owner_engine.begin() as conn:
        rid = _insert_registry(conn)
        conn.execute(
            text("INSERT INTO spec.spec_trigger VALUES (:r, 'usecase.submitted')"), {"r": rid}
        )
        conn.execute(
            text(
                "INSERT INTO spec.spec_outcome_route (spec_registry_id, outcome_status, root_cause, "
                "destination_kind, destination) VALUES (:r, 'pass', NULL, 'terminal', 'T1')"
            ),
            {"r": rid},
        )
        conn.execute(
            text(
                "INSERT INTO spec.spec_event_route (spec_registry_id, event_type, destination_kind, "
                "destination) VALUES (:r, 'T8.event.drift', 'terminal', 'T9')"
            ),
            {"r": rid},
        )
        conn.execute(
            text(
                "INSERT INTO spec.spec_change_class (spec_registry_id, change_class, reentry_terminal) "
                "VALUES (:r, 'minor', 'T3')"
            ),
            {"r": rid},
        )
        conn.execute(
            text(
                "INSERT INTO spec.spec_timeline (spec_registry_id, risk_tier, expected_duration, "
                "continuous, reminder_after, escalate_after, escalate_at_window_end, "
                "max_rework_cycles, clarification_sla, max_clarification_rounds) "
                "VALUES (:r, 'low', '2d', false, '2d', '7d', false, 3, '2d', 2)"
            ),
            {"r": rid},
        )
        conn.execute(
            text(
                "INSERT INTO spec.spec_catalogue (catalogue_name, version, status, content_json, "
                "content_hash) VALUES ('roles', '1.0.0', 'active', '{}'::jsonb, :h)"
            ),
            {"h": HASH},
        )
        conn.execute(
            text(
                "INSERT INTO spec.playbook_registry (playbook_id, version, path, content_hash) "
                "VALUES ('PB-T0-01', '1.0.0', 'playbooks/t0-intake.md', :h)"
            ),
            {"h": HASH},
        )
    yield rid


def _refused(engine: Engine, sql: str, **params: object) -> None:
    with pytest.raises(DBAPIError) as excinfo, engine.begin() as conn:
        conn.execute(text(sql), params)
    assert getattr(excinfo.value.orig, "sqlstate", None) == "42501", excinfo.value


ALL_TABLES = ("spec_registry", "spec_catalogue", "playbook_registry", *PROJECTIONS)


@pytest.mark.parametrize("table", ALL_TABLES)
def test_delete_and_truncate_refused_for_owner(
    owner_engine: Engine, seeded: int, table: str
) -> None:
    _refused(owner_engine, f"DELETE FROM spec.{table}")
    _refused(owner_engine, f"TRUNCATE spec.{table} CASCADE")


@pytest.mark.parametrize("table", ["playbook_registry", *PROJECTIONS])
def test_updates_refused_for_owner(owner_engine: Engine, seeded: int, table: str) -> None:
    column = {"playbook_registry": "path"}.get(table, "spec_registry_id")
    value = "'x'" if column == "path" else column
    _refused(owner_engine, f"UPDATE spec.{table} SET {column} = {value}")


@pytest.mark.parametrize("table", ALL_TABLES)
def test_app_identity_read_only(app_engine: Engine, seeded: int, table: str) -> None:
    with app_engine.connect() as conn:
        conn.execute(text(f"SELECT * FROM spec.{table}")).all()
    with pytest.raises(ProgrammingError), app_engine.begin() as conn:
        conn.execute(text(f"DELETE FROM spec.{table}"))


def test_permitted_status_transitions(owner_engine: Engine, seeded: int) -> None:
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE spec.spec_registry SET status='deprecated', deprecated_at=now() "
                "WHERE spec_registry_id=:r"
            ),
            {"r": seeded},
        )
        conn.execute(
            text(
                "UPDATE spec.spec_registry SET status='retired', retired_at=now() WHERE spec_registry_id=:r"
            ),
            {"r": seeded},
        )
        conn.execute(text("UPDATE spec.spec_catalogue SET status='deprecated'"))
    _refused(owner_engine, "UPDATE spec.spec_registry SET status='active'")


def test_other_columns_frozen(owner_engine: Engine, seeded: int) -> None:
    _refused(owner_engine, "UPDATE spec.spec_registry SET version='9.9.9'")
    _refused(
        owner_engine, "UPDATE spec.spec_registry SET status='deprecated', content_hash=:h", h=HASH_B
    )
    _refused(owner_engine, "UPDATE spec.spec_catalogue SET content_hash=:h", h=HASH_B)


def test_one_active_version_per_terminal(owner_engine: Engine, seeded: int) -> None:
    with pytest.raises(IntegrityError), owner_engine.begin() as conn:
        _insert_registry(conn, version="1.1.0")


def test_retiring_pinned_version_refused(owner_engine: Engine, seeded: int) -> None:
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO spec.usecase_spec_pin (usecase_id, terminal_id, version, pinned_reason) "
                "VALUES ('UC-0001', 'T0', '1.0.0', 'T0 start')"
            )
        )
    _refused(owner_engine, "UPDATE spec.spec_registry SET status='retired', retired_at=now()")


def test_hash_format_enforced(owner_engine: Engine, seeded: int) -> None:
    with pytest.raises(IntegrityError), owner_engine.begin() as conn:
        _insert_registry(conn, terminal="T1", content_hash="sha256:bad")
