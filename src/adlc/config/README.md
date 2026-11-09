# adlc.config

Typed settings read from the environment only (feature 001; contracts/settings.md).

- `DatabaseSettings`: `ADLC_ENV` and `ADLC_DB_*`. Used by migrations and `make migration-check`.
- `Settings(DatabaseSettings)`: adds session, account-file, role-catalogue, tracing and logging settings. Used by `adlc-api` and `adlc-account`.
- `Duration`: `<int><unit>` with unit `s`, `min`, `h` or `d`. A bare `m` is rejected, because TDS Annex B.1 uses it for months.
- `load_settings_or_exit(model)`: on any problem, prints `adlc: configuration error` with one line per setting (name, `missing`/`invalid`, expected form) and exits with code 2. Values are never printed.

Secret fields are `SecretStr`. Each field's expected form and secret flag live in `json_schema_extra`, and `tests/unit/test_env_example.py` keeps `.env.example` in step with the model.
