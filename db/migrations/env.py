"""Alembic environment: the platform SQLite file, built from DatabaseSettings (created if missing)."""

from logging.config import fileConfig

from alembic import context

from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import DatabaseSettings
from adlc.db.engine import open_engine

config = context.config
if config.config_file_name is not None and not config.attributes.get("skip_logging"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def run_migrations_online() -> None:
    settings = load_settings_or_exit(DatabaseSettings)
    engine = open_engine(settings, create=True)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=None,
                transaction_per_migration=True,
                transactional_ddl=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline migrations are not supported; run against a database")
run_migrations_online()
