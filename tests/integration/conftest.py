from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Engine

from adlc.config.settings import Settings
from tests.support.db import REPO_ROOT, PlatformDatabase, alembic

if TYPE_CHECKING:
    from tests.support.orchestration import Harness


@pytest.fixture
def platform_db(tmp_path: Path) -> PlatformDatabase:
    """A database file that does not exist yet (the migrations create it)."""
    return PlatformDatabase(tmp_path / "adlc.db")


@pytest.fixture
def migrated_db(platform_db: PlatformDatabase) -> PlatformDatabase:
    alembic(platform_db, "upgrade", "head")
    return platform_db


@pytest.fixture
def engine(migrated_db: PlatformDatabase) -> Iterator[Engine]:
    """The migrated database, opened as every platform process opens it."""
    built = migrated_db.engine()
    yield built
    built.dispose()


# The platform has one database identity; older suites name it by its two former roles.
@pytest.fixture
def owner_engine(engine: Engine) -> Engine:
    return engine


@pytest.fixture
def app_engine(engine: Engine) -> Engine:
    return engine


@pytest.fixture
def api_settings(migrated_db: PlatformDatabase, tmp_path: Path) -> Settings:
    """Settings for an API process talking to the test database."""
    accounts = tmp_path / "accounts.yaml"
    accounts.write_text("accounts: []\n")
    return settings_for(migrated_db, accounts)


def settings_for(db: PlatformDatabase, accounts_file: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "env": "dev",
        "db_path": db.path,
        "session_secret": "test-session-secret-" + "x" * 20,
        "accounts_file": accounts_file,
        "role_catalogue": REPO_ROOT / "adlc-specs" / "shared" / "roles.yaml",
        "db_connect_timeout": "5s",
        "db_busy_timeout": "10s",
        "deadletter_role": "adlc_coe",  # 007: the API serves dead letters to this role
    }
    values.update(overrides)
    return Settings.model_validate(values)


# ------------------------------------------------------------------ orchestration and policy (003, 004)


@pytest.fixture(scope="session")
def orch_template(tmp_path_factory: pytest.TempPathFactory) -> PlatformDatabase:
    """Migrated database with the real adlc-specs registered, copied for each test."""
    from tests.support.orchestration import build_template

    return build_template(PlatformDatabase(tmp_path_factory.mktemp("template") / "adlc.db"))


@pytest.fixture
def h(orch_template: PlatformDatabase) -> Iterator["Harness"]:
    from tests.support.orchestration import harness

    with harness(orch_template) as built:
        yield built
