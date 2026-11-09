"""Disposable PostgreSQL for tests and ``make migration-check``.

Starts the same image as ``deploy/compose.yaml`` and runs the same init script, so tests see
the same two identities as the real environment. Passwords are random per run.
"""

import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from alembic import command
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parents[2]
INIT_DIR = REPO_ROOT / "deploy" / "postgres" / "init"
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
PG_IMAGE = "postgres:16.15"  # keep in step with deploy/compose.yaml


@dataclass(frozen=True)
class PlatformDatabase:
    host: str
    port: int
    owner_password: str
    app_password: str
    owner_user: str = "adlc_owner"
    app_user: str = "adlc_app"
    name: str = "adlc"
    superuser_password: str = field(default="", repr=False)

    def url(self, user: str, password: str) -> str:
        return f"postgresql+psycopg://{user}:{password}@{self.host}:{self.port}/{self.name}"

    @property
    def owner_url(self) -> str:
        return self.url(self.owner_user, self.owner_password)

    @property
    def app_url(self) -> str:
        return self.url(self.app_user, self.app_password)

    @property
    def env(self) -> dict[str, str]:
        """``ADLC_*`` settings pointing at this database."""
        return {
            "ADLC_ENV": "dev",
            "ADLC_DB_HOST": self.host,
            "ADLC_DB_PORT": str(self.port),
            "ADLC_DB_NAME": self.name,
            "ADLC_DB_OWNER_USER": self.owner_user,
            "ADLC_DB_OWNER_PASSWORD": self.owner_password,
            "ADLC_DB_APP_USER": self.app_user,
            "ADLC_DB_APP_PASSWORD": self.app_password,
        }


@contextmanager
def platform_postgres() -> Iterator[PlatformDatabase]:
    owner_pw, app_pw, super_pw = (secrets.token_urlsafe(24) for _ in range(3))
    container = (
        PostgresContainer(PG_IMAGE, username="postgres", password=super_pw, dbname="postgres")
        .with_env("ADLC_DB_OWNER_PASSWORD", owner_pw)
        .with_env("ADLC_DB_APP_PASSWORD", app_pw)
        .with_volume_mapping(str(INIT_DIR), "/docker-entrypoint-initdb.d", "ro")
    )
    with container:
        yield PlatformDatabase(
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(5432)),
            owner_password=owner_pw,
            app_password=app_pw,
            superuser_password=super_pw,
        )


@contextmanager
def patched_env(values: dict[str, str]) -> Iterator[None]:
    saved = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def alembic(db: PlatformDatabase, *args: str) -> None:
    """Run an Alembic command against ``db`` with the owner identity."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(REPO_ROOT / "db" / "migrations"))
    with patched_env(db.env):
        verb, *rest = args
        if verb == "upgrade":
            command.upgrade(config, rest[0])
        elif verb == "downgrade":
            command.downgrade(config, rest[0])
        elif verb == "stamp":
            command.stamp(config, rest[0], purge=True)
        else:
            raise ValueError(f"unsupported alembic command: {verb}")
