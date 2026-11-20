# adlc.db

The platform data store: one SQLite file (`ADLC_DB_PATH`) shared by every platform process on
one host (feature 001; data-model.md; changed from PostgreSQL on the `feature/sqlite` branch).

- `open_engine(settings, create=False)`: the engine every process uses. Only the migrations pass
  `create=True`; a service never creates the file, it waits for it.
- `database_engine(path, busy_timeout)`: the same, from a path (tests and tools).
- `wait_for_database(engine, timeout)`: retries `SELECT 1` until the file exists and answers, then
  raises `DatabaseUnavailable` naming the path.

Every connection runs in write-ahead-log mode with foreign keys on and a busy timeout
(`ADLC_DB_BUSY_TIMEOUT`). An explicit transaction (`engine.begin()`) starts with
`BEGIN IMMEDIATE` and holds the one write lock until it ends: two workers can never claim the same
outbox event, timer or run. A connection that only reads (`engine.connect()`) starts a plain
`BEGIN` and never waits for a writer. A transaction must not write through a second connection
while it holds the lock: the second connection would wait for the first until the busy timeout.

Values: columns declared `timestamptz`, `date`, `jsonb`, `boolean`, `numeric` and `uuid` come
back as Python `datetime` (UTC), `date`, JSON values, `bool`, `Decimal` and `UUID`; an expression is
typed by its alias, e.g. `max(at) AS "at [timestamptz]"`. Lists and dicts are stored as JSON text;
a list parameter is matched with `IN (SELECT value FROM json_each(:ids))`. Times are ISO 8601 text
in UTC with microseconds, so text order is time order.

The schema lives in `db/migrations` (Alembic, one baseline revision). Triggers refuse UPDATE and
DELETE on the ledger and every other append-only table for every connection. SQLite has no
database identities, so a process with write access to the file could drop a trigger; the hash
chain (`adlc-ledger verify`) detects any changed or removed record. This is an accepted limit.
