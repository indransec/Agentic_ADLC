"""Board engagement: the change request kind (feature 020).

``board_link.object_kind`` gains ``change`` (a release's ITSM change request shown on the board).
SQLite cannot alter a CHECK constraint, so the table is rebuilt with its rows. ``board_link`` is
not append-only. The history tables are untouched: a change decision is claimed as ``decide``.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-21
"""

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None

NOW = "(now())"


def _board_link(name: str, kinds: str) -> str:
    return f"""
        CREATE TABLE {name} (
            object_kind text NOT NULL CHECK (object_kind IN {kinds}),
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


def _rebuild(kinds: str, keep: str = "1 = 1") -> None:
    op.execute(_board_link("board_link_rebuilt", kinds))
    op.execute(f"INSERT INTO board_link_rebuilt SELECT * FROM board_link WHERE {keep}")
    op.execute("DROP TABLE board_link")
    op.execute("ALTER TABLE board_link_rebuilt RENAME TO board_link")


def upgrade() -> None:
    _rebuild("('usecase', 'run', 'clarification', 'change')")


def downgrade() -> None:
    _rebuild("('usecase', 'run', 'clarification')", keep="object_kind <> 'change'")
