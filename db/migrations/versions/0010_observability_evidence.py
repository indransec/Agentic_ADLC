"""Observability and monitoring results as evidence (012 research R-06, data-model.md).

T7 copies stage metrics read from observability and T6 copies the monitors it configured; both
are checked against the recorded results, so these results are recorded like other evidence.
Only the kind check of ``tools.tool_result`` changes; grants are unchanged.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-12
"""

from typing import Any

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None

BEFORE = ("ci", "harness", "redteam", "dlp", "deploy", "traffic", "kill_switch", "environment")
AFTER = (*BEFORE, "observability", "monitoring")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _kinds(values: tuple[str, ...], *, existing_rows: bool) -> None:
    op.execute("ALTER TABLE tools.tool_result DROP CONSTRAINT tool_result_kind_check")
    op.execute(
        "ALTER TABLE tools.tool_result ADD CONSTRAINT tool_result_kind_check "
        f"CHECK (kind IN ({_in(values)})){'' if existing_rows else ' NOT VALID'}"
    )


def upgrade(**kwargs: Any) -> None:
    _kinds(AFTER, existing_rows=True)


def downgrade(**kwargs: Any) -> None:
    # Results are append-only for every identity: rows of the new kinds stay, and the narrower
    # check applies to new rows only (NOT VALID).
    _kinds(BEFORE, existing_rows=False)
