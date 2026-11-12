"""T002: migration 0010 (012 data-model.md): observability and monitoring results are evidence."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from adlc.tools.catalogue import EVIDENCE_KINDS
from tests.integration.tools.test_migration_0009 import _call, _result
from tests.support.pg import PlatformDatabase, alembic


@pytest.mark.parametrize("kind", ["observability", "monitoring"])
def test_new_evidence_kinds_are_accepted(app_engine: Engine, kind: str) -> None:
    with app_engine.begin() as conn:
        conn.execute(text(_call()))
        conn.execute(text(_result(kind=f"'{kind}'", package="NULL")))


def test_every_catalogue_evidence_kind_is_allowed(app_engine: Engine) -> None:
    with app_engine.begin() as conn:
        conn.execute(text(_call()))
        for kind in EVIDENCE_KINDS:
            conn.execute(text(_result(kind=f"'{kind}'", package="NULL")))


def test_unknown_kind_still_refused(app_engine: Engine) -> None:
    with pytest.raises(DBAPIError), app_engine.begin() as conn:
        conn.execute(text(_call()))
        conn.execute(text(_result(kind="'other'")))


def test_round_trip(migrated_db: PlatformDatabase) -> None:
    alembic(migrated_db, "downgrade", "0009")
    alembic(migrated_db, "upgrade", "head")
