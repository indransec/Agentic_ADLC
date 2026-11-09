"""Baseline: four owned schemas and the append-only ledger record table.

data-model.md (001); FR-006, FR-009, FR-011; spec clarification 1.
Ledger rows are refused UPDATE, DELETE and TRUNCATE for every identity by triggers; only a
DROP of the whole table (downgrade or reset) removes ledger data.

Revision ID: 0001
Revises:
Create Date: 2026-11-09
"""

from typing import Any

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

SCHEMAS = ("spec", "run", "ledger", "events")
HASH_PATTERN = "^sha256:[0-9a-f]{64}$"


def _role(kwargs: dict[str, Any]) -> str:
    """Application role name, validated by DatabaseSettings and passed in by env.py."""
    role = kwargs.get("app_role")
    if not isinstance(role, str) or not role:
        raise RuntimeError("app_role not supplied by env.py")
    return role


def upgrade(**kwargs: Any) -> None:
    app = op.get_context().dialect.identifier_preparer.quote(_role(kwargs))

    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA {schema}")
        op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {app}")

    op.execute(
        f"""
        CREATE TABLE ledger.ledger_record (
            ledger_record_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            ledger_key text NOT NULL UNIQUE,
            content_hash text NOT NULL
                CHECK (content_hash ~ '{HASH_PATTERN}'),
            previous_record_hash text NULL
                CHECK (previous_record_hash IS NULL OR previous_record_hash ~ '{HASH_PATTERN}'),
            written_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE FUNCTION ledger.reject_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'ledger.ledger_record is append-only: % refused', TG_OP
                USING ERRCODE = '42501';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER ledger_record_no_update_delete
        BEFORE UPDATE OR DELETE ON ledger.ledger_record
        FOR EACH ROW EXECUTE FUNCTION ledger.reject_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER ledger_record_no_truncate
        BEFORE TRUNCATE ON ledger.ledger_record
        FOR EACH STATEMENT EXECUTE FUNCTION ledger.reject_mutation()
        """
    )
    op.execute("REVOKE ALL ON ledger.ledger_record FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON ledger.ledger_record TO {app}")
    op.execute(f"GRANT USAGE ON SEQUENCE ledger.ledger_record_ledger_record_id_seq TO {app}")


def downgrade(**kwargs: Any) -> None:
    op.execute("DROP TRIGGER ledger_record_no_truncate ON ledger.ledger_record")
    op.execute("DROP TRIGGER ledger_record_no_update_delete ON ledger.ledger_record")
    op.execute("DROP TABLE ledger.ledger_record")
    op.execute("DROP FUNCTION ledger.reject_mutation()")
    for schema in reversed(SCHEMAS):
        op.execute(f"DROP SCHEMA {schema} RESTRICT")
