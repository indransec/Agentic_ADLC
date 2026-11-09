"""Alembic environment: always connects as the schema owner, built from DatabaseSettings."""

from logging.config import fileConfig

from alembic import context

from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import DatabaseSettings
from adlc.db.engine import owner_engine

config = context.config
if config.config_file_name is not None and not config.attributes.get("skip_logging"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def run_migrations_online() -> None:
    settings = load_settings_or_exit(DatabaseSettings)
    engine = owner_engine(settings)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=None,
                version_table_schema="public",
                transaction_per_migration=True,
            )
            with context.begin_transaction():
                context.run_migrations(app_role=settings.db_app_user)
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline migrations are not supported; run against a database")
run_migrations_online()
