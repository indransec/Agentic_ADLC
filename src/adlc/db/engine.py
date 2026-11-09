"""Engine factories for the two data store identities (data-model.md, FR-010).

The schema-owner engine is for migrations only; running services use the application engine.
"""

import logging
import time
from datetime import timedelta

from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from adlc.config.settings import DatabaseSettings, Settings

log = logging.getLogger(__name__)


class ConfigurationError(RuntimeError):
    """A setting needed for this operation is missing."""


class DatabaseUnavailable(RuntimeError):
    """The data store did not answer within the configured timeout."""


def _url(settings: DatabaseSettings, user: str, password: str) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=user,
        password=password,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
    )


def owner_url(settings: DatabaseSettings) -> URL:
    if settings.db_owner_password is None:
        raise ConfigurationError(
            "ADLC_DB_OWNER_PASSWORD: missing; expected at least 16 characters (secret)"
        )
    return _url(settings, settings.db_owner_user, settings.db_owner_password.get_secret_value())


def app_url(settings: Settings) -> URL:
    return _url(settings, settings.db_app_user, settings.db_app_password.get_secret_value())


def owner_engine(settings: DatabaseSettings) -> Engine:
    return create_engine(owner_url(settings), pool_pre_ping=True)


def app_engine(settings: Settings) -> Engine:
    return create_engine(
        app_url(settings),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 2},
    )


def wait_for_database(engine: Engine, timeout: timedelta, interval: float = 1.0) -> None:
    """Retry ``SELECT 1`` until it succeeds or ``timeout`` passes.

    The error names host and port, never credentials.
    """
    deadline = time.monotonic() + timeout.total_seconds()
    target = f"{engine.url.host}:{engine.url.port}"
    while True:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except OperationalError:
            if time.monotonic() >= deadline:
                raise DatabaseUnavailable(
                    f"database at {target} not reachable within {int(timeout.total_seconds())}s"
                ) from None
            log.info("waiting for database at %s", target)
            time.sleep(interval)
