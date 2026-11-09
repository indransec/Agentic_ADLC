# adlc.db

Engines for the two data store identities (feature 001; data-model.md).

- `owner_engine(settings)`: the schema owner (`ADLC_DB_OWNER_*`), for migrations only.
- `app_engine(settings)`: the application identity (`ADLC_DB_APP_*`), for running services.
- `wait_for_database(engine, timeout)`: retries `SELECT 1`, then raises `DatabaseUnavailable` naming host and port, never credentials.

The schema itself lives in `db/migrations` (Alembic). `ledger.ledger_record` is append-only for **every** identity: triggers refuse UPDATE, DELETE and TRUNCATE, and only a downgrade or reset (DROP TABLE) removes ledger data. The container superuser is used only by `deploy/postgres/init/01-roles.sh` and can bypass triggers; this is an accepted MVP limit.
