"""Board engagement (feature 016): links, sync state, delivery, inbound changes, reconciliation.

Tables of ``specs/016-engagement-layer/data-model.md``. History tables (``board_requeue``,
``inbound_change``, ``inbound_outcome``, ``board_reconciliation``) are append-only: triggers refuse
UPDATE and DELETE for every connection, as for the ledger.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-21
"""

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None

NOW = "(now())"
APPEND_ONLY = ("board_requeue", "inbound_change", "inbound_outcome", "board_reconciliation")
TABLES = (
    "board_link",
    "board_sync_state",
    "board_delivery",
    "board_requeue",
    "inbound_change",
    "inbound_outcome",
    "board_reconciliation",
)
OBJECT_KINDS = "('usecase', 'run', 'clarification')"
POLL_OUTCOMES = "('ok', 'board_unreachable', 'auth_failed', 'mapping_invalid')"
CHANGE_KINDS = (
    "('own', 'baseline', 'register_usecase', 'decide', 'answer', 'revert_only', 'ignored')"
)
OUTCOMES = "('accepted', 'refused', 'ignored')"
REASON_CODES = (
    "('not_mapped', 'not_authorised', 'missing_input', 'invalid_input', 'stale', "
    "'already_answered', 'unknown_value', 'closed', 'platform_field', 'invalid_usecase')"
)


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE board_link (
            object_kind text NOT NULL CHECK (object_kind IN {OBJECT_KINDS}),
            object_id text NOT NULL CHECK (length(object_id) BETWEEN 1 AND 200),
            work_item_id integer NOT NULL UNIQUE CHECK (work_item_id > 0),
            item_type text NOT NULL,
            projected_hash text NULL,
            last_written_rev integer NULL,
            inbound_update_id integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT {NOW},
            updated_at timestamptz NOT NULL DEFAULT {NOW},
            PRIMARY KEY (object_kind, object_id)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE board_sync_state (
            id integer PRIMARY KEY CHECK (id = 1),
            watermark text NULL,
            last_poll_at timestamptz NULL,
            last_poll_outcome text NULL CHECK (last_poll_outcome IN {POLL_OUTCOMES}),
            last_error text NULL CHECK (length(last_error) <= 2000),
            projection_cursor jsonb NOT NULL DEFAULT '{{}}'
        )
        """
    )
    op.execute("INSERT INTO board_sync_state (id) VALUES (1)")
    op.execute(
        """
        CREATE TABLE board_delivery (
            usecase_id text PRIMARY KEY REFERENCES usecase (usecase_id),
            dirty_since timestamptz NULL,
            attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            next_attempt_at timestamptz NULL,
            dead_lettered_at timestamptz NULL,
            last_error text NULL CHECK (length(last_error) <= 2000),
            delivered_at timestamptz NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX board_delivery_due ON board_delivery (next_attempt_at) "
        "WHERE dirty_since IS NOT NULL AND dead_lettered_at IS NULL"
    )
    op.execute(
        f"""
        CREATE TABLE board_requeue (
            board_requeue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            usecase_id text NOT NULL REFERENCES usecase (usecase_id),
            actor text NOT NULL,
            at timestamptz NOT NULL DEFAULT {NOW}
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE inbound_change (
            work_item_id integer NOT NULL CHECK (work_item_id > 0),
            update_id integer NOT NULL CHECK (update_id > 0),
            rev integer NOT NULL CHECK (rev > 0),
            changer text NOT NULL,
            account_name text NULL,
            kind text NOT NULL CHECK (kind IN {CHANGE_KINDS}),
            object_id text NULL,
            read_at timestamptz NOT NULL DEFAULT {NOW},
            PRIMARY KEY (work_item_id, update_id)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE inbound_outcome (
            work_item_id integer NOT NULL,
            update_id integer NOT NULL,
            outcome text NOT NULL CHECK (outcome IN {OUTCOMES}),
            reason_code text NULL CHECK (reason_code IS NULL OR reason_code IN {REASON_CODES}),
            reason text NULL CHECK (length(reason) <= 2000),
            command text NULL,
            reverted boolean NOT NULL DEFAULT FALSE,
            at timestamptz NOT NULL DEFAULT {NOW},
            PRIMARY KEY (work_item_id, update_id),
            FOREIGN KEY (work_item_id, update_id)
                REFERENCES inbound_change (work_item_id, update_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE board_reconciliation (
            board_reconciliation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_by text NOT NULL,
            started_at timestamptz NOT NULL,
            ended_at timestamptz NOT NULL,
            outcome text NOT NULL CHECK (outcome IN ('ok', 'failed')),
            items_checked integer NOT NULL DEFAULT 0,
            created_items integer NOT NULL DEFAULT 0,
            differences jsonb NOT NULL DEFAULT '[]',
            error text NULL CHECK (length(error) <= 2000)
        )
        """
    )
    for table in APPEND_ONLY:
        for event in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER {table}_no_{event.lower()} BEFORE {event} ON {table} "
                f"BEGIN SELECT RAISE(ABORT, '{table} is append-only: {event} refused'); END"
            )


def downgrade() -> None:
    for table in APPEND_ONLY:
        for event in ("update", "delete"):
            op.execute(f"DROP TRIGGER {table}_no_{event}")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
