from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Engine, create_engine

from adlc.config.settings import Settings
from tests.support.pg import REPO_ROOT, PlatformDatabase, alembic, platform_postgres

if TYPE_CHECKING:
    from tests.support.orchestration import Harness


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


@pytest.fixture
def api_settings(platform_db: PlatformDatabase, tmp_path: Path) -> Settings:
    """Settings for an API process talking to the test database as the app identity."""
    accounts = tmp_path / "accounts.yaml"
    accounts.write_text("accounts: []\n")
    return settings_for(platform_db, accounts)


def settings_for(db: PlatformDatabase, accounts_file: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "env": "dev",
        "db_host": db.host,
        "db_port": db.port,
        "db_app_password": db.app_password,
        "db_owner_password": db.owner_password,
        "session_secret": "test-session-secret-" + "x" * 20,
        "accounts_file": accounts_file,
        "role_catalogue": REPO_ROOT / "adlc-specs" / "shared" / "roles.yaml",
        "db_connect_timeout": "5s",
    }
    values.update(overrides)
    return Settings.model_validate(values)


# ------------------------------------------------------------------ orchestration and policy (003, 004)


@pytest.fixture(scope="session")
def orch_template(platform_db: PlatformDatabase) -> PlatformDatabase:
    """Migrated database with the real adlc-specs registered, copied for each test."""
    from tests.support.orchestration import build_template

    build_template(platform_db)
    return platform_db


@pytest.fixture
def h(orch_template: PlatformDatabase) -> Iterator["Harness"]:
    from tests.support.orchestration import harness

    with harness(orch_template) as built:
        yield built
