from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine

from tests.support.pg import PlatformDatabase, alembic, platform_postgres


@pytest.fixture(scope="session")
def platform_db() -> Iterator[PlatformDatabase]:
    with platform_postgres() as db:
        yield db


@pytest.fixture
def migrated_db(platform_db: PlatformDatabase) -> Iterator[PlatformDatabase]:
    alembic(platform_db, "upgrade", "head")
    try:
        yield platform_db
    finally:
        alembic(platform_db, "downgrade", "base")


@pytest.fixture
def owner_engine(migrated_db: PlatformDatabase) -> Iterator[Engine]:
    engine = create_engine(migrated_db.owner_url)
    yield engine
    engine.dispose()


@pytest.fixture
def app_engine(migrated_db: PlatformDatabase) -> Iterator[Engine]:
    engine = create_engine(migrated_db.app_url)
    yield engine
    engine.dispose()
