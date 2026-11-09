---
description: "Task list for 001-platform-foundation"
---

# Tasks: Platform Foundation

**Input**: Design documents from `specs/001-platform-foundation/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Required. Constitution IX requires every feature to ship with tests and requires
test-first work for core rules. Test tasks in each story come first and must fail before the
implementation tasks start.

**Organization**: Tasks are grouped by user story. The three P1 stories run in dependency
order (US2 migrations → US3 configuration → US1 environment), because the environment starts
the migration service and needs validated settings.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: User story from spec.md (US1–US6)
- Paths are repository-relative; layout per plan.md "Source Code"

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton, tooling and the layout from build plan §5

- [X] T001 Create the repository layout from plan.md: `src/adlc/{config,db,identity,observability,api,cli}/__init__.py`, `src/adlc/__init__.py`, `db/migrations/versions/`, `deploy/postgres/init/`, `tests/{unit,integration,scenario}/`, `adlc-specs/{terminals,shared,playbooks,checklists,schema}/`, `mcp_servers/`, `pilot/`, `.github/workflows/`
- [X] T002 [P] Add placeholder READMEs naming the feature that fills each one: `src/adlc/spec_toolkit/README.md` (002), `src/adlc/orchestration/README.md` (003), `src/adlc/policy/README.md` (004), `src/adlc/ledger/README.md` (005), `src/adlc/agents/README.md` (006, 008, 011, 012), `src/adlc/ui/README.md` (007, 013), `adlc-specs/terminals/README.md`, `adlc-specs/playbooks/README.md`, `adlc-specs/checklists/README.md`, `adlc-specs/schema/README.md` (002), `mcp_servers/README.md` (008, 010), `pilot/README.md` (009), `tests/scenario/README.md` (014); each also gets an empty `__init__.py` where it is a Python package
- [X] T003 Create `pyproject.toml` for uv: Python `>=3.12,<3.13`, src layout, package `adlc`; runtime deps fastapi, pydantic, pydantic-settings, uvicorn, sqlalchemy, alembic, psycopg[binary], ruamel.yaml, typer, itsdangerous, opentelemetry-api, opentelemetry-sdk, opentelemetry-exporter-otlp-proto-http, opentelemetry-instrumentation-fastapi; dev deps pytest, pytest-cov, httpx, testcontainers[postgres], ruff, mypy; scripts `adlc-api = "adlc.api.__main__:main"` and `adlc-account = "adlc.cli.account:app"`; then run `uv lock`
- [X] T004 Add tool config to `pyproject.toml`: ruff (line length 100, rules E,F,I,B,UP,S,N,SIM), `[tool.mypy] strict = true` over `src` and `tests`, pytest markers `integration` and `testpaths = ["tests"]`
- [X] T005 [P] Create `Makefile` with every target in contracts/make-targets.md. Implement `install`, `lint`, `typecheck` and `test` now (`uv sync --locked`, `uv run ruff check . && uv run ruff format --check .`, `uv run mypy src tests`, `uv run pytest`). Leave the other targets as stubs that print `not implemented yet` and exit 1. Each target echoes `==> <target>` first, so a failure names its step

**Checkpoint**: `make install lint typecheck` passes on the empty package.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Settings model, database access and the app factory that every story uses

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T006 [P] Write failing unit tests for duration parsing in `tests/unit/test_durations.py`: `8h`, `90s`, `30min` and `7d` parse to a `timedelta`; bare `m`, `10`, `-1h` and `1.5h` are rejected (research R-06, contracts/settings.md "Duration form: `<int><unit>` with unit `s`, `min`, `h` or `d`")
- [X] T007 [P] Implement the `Duration` type and parser in `src/adlc/config/durations.py` so T006 passes
- [X] T008 Implement two pydantic-settings models (`env_prefix="ADLC_"`) in `src/adlc/config/settings.py`. `DatabaseSettings` holds only `env` and the `db_*` fields and is used by migrations, `migrate` and `migration-check`. `Settings(DatabaseSettings)` adds the API fields and is used by `adlc-api` and `adlc-account`. Together they cover every row of contracts/settings.md: `env: Literal["dev","demo"]`; `db_host` required; `db_port` int 1–65535 default 5432; `db_name` default `adlc`; `db_app_user` default `adlc_app`; `db_app_password: SecretStr` required, min 16; `db_owner_user` default `adlc_owner`; `db_owner_password: SecretStr | None`, min 16 when set; `db_connect_timeout: Duration` default `60s`; `session_secret: SecretStr` required, min 32; `session_ttl: Duration` default `8h`; `accounts_file: Path` required; `role_catalogue: Path` default `adlc-specs/shared/roles.yaml`; `otlp_endpoint` default `http://jaeger:4318`; `log_level` in DEBUG/INFO/WARNING/ERROR default INFO. Mark each field's secret flag in field metadata, for use in error output
- [X] T009 [P] Implement the engine factory in `src/adlc/db/engine.py`: `app_engine(settings)` and `owner_engine(settings)` (psycopg 3 URLs built from settings; the owner engine raises a config error naming `ADLC_DB_OWNER_PASSWORD` when it is unset), plus `wait_for_database(engine, timeout)`, which retries `SELECT 1` and then raises `DatabaseUnavailable` naming host and port, never the password
- [X] T010 [P] Write `deploy/postgres/init/01-roles.sh` (bash, `set -euo pipefail`): create login roles `${ADLC_DB_OWNER_USER}` and `${ADLC_DB_APP_USER}` with passwords from env, create database `${ADLC_DB_NAME}` owned by the owner role, grant `CONNECT` to the app role, and revoke `CREATE` on schema `public` from `PUBLIC` (data-model.md "Database identities")
- [X] T011 Create integration fixtures in `tests/integration/conftest.py`: a session-scoped testcontainers `postgres:16` container whose init runs `deploy/postgres/init/01-roles.sh` with test passwords; fixtures `owner_url` and `app_url`; a function-scoped `migrated_db` fixture that runs `alembic upgrade head` as owner and `downgrade base` afterwards; mark the module `integration`
- [X] T012 [P] Implement logging setup in `src/adlc/observability/logging.py`: stdlib logging, level from settings, a format without request headers, and a filter that drops any record attribute named `authorization`, `password`, `token` or `credential_hash`
- [X] T013 Implement `create_app(settings)` in `src/adlc/api/app.py`: FastAPI app, settings stored on `app.state`, logging configured, routers registered; plus `src/adlc/api/__main__.py` `main()`, which loads `Settings`, calls `wait_for_database`, and runs uvicorn on 0.0.0.0:8000

**Checkpoint**: settings load from env, the test database fixture starts, and the app factory builds.

---

## Phase 3: User Story 2 - Versioned schema changes over four owned data areas (Priority: P1)

**Goal**: Alembic migrations create `spec`, `run`, `ledger` and `events` with an append-only `ledger.ledger_record` that every identity is refused on update, delete and truncate.

**Independent Test**: on an empty database, `upgrade head` → the four schemas and the table exist; app identity can insert and select; update, delete and truncate are refused for app and owner; `downgrade base` → empty.

### Tests for User Story 2 (write first, must fail) ⚠️

- [X] T014 [P] [US2] Write `tests/integration/test_migrations.py`: upgrade creates schemas `spec`, `run`, `ledger`, `events` owned by `adlc_owner`; `alembic_version` holds `0001`; running upgrade again changes nothing; `downgrade base` removes the four schemas and the table; upgrade → downgrade → upgrade succeeds 10 times in a row (SC-003); a database stamped with an unknown revision makes `upgrade` fail with an error naming the revision
- [X] T015 [P] [US2] Write `tests/integration/test_ledger_immutability.py` (core rule, constitution IX): as `adlc_app`, INSERT and SELECT on `ledger.ledger_record` succeed; as `adlc_app`, UPDATE, DELETE and TRUNCATE each fail; as `adlc_owner`, UPDATE, DELETE and TRUNCATE each fail with SQLSTATE `42501` and a message containing `ledger.ledger_record is append-only`; the row is unchanged after every attempt; `content_hash` not matching `^sha256:[0-9a-f]{64}$` is rejected; `previous_record_hash` may be null but is rejected when set to a bad format; a duplicate `ledger_key` is rejected; `adlc_app` has no privileges on any other schema object

### Implementation for User Story 2

- [X] T016 [US2] Create `alembic.ini` at the repo root (`script_location = db/migrations`) and `db/migrations/env.py`, which builds its URL from `DatabaseSettings` through `owner_engine` (so it uses the owner identity only and does not need API-only settings such as `ADLC_ACCOUNTS_FILE`), with `version_table_schema = "public"` and online mode only
- [X] T017 [US2] Write migration `db/migrations/versions/0001_baseline.py` (revision `0001`) per data-model.md. Upgrade: `CREATE SCHEMA spec, run, ledger, events`; `GRANT USAGE` on each to the app role (name from `ADLC_DB_APP_USER`, read in the migration through `DatabaseSettings`, not hard-coded); create `ledger.ledger_record` with `ledger_record_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY`, `ledger_key text NOT NULL UNIQUE`, `content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$')`, `previous_record_hash text NULL CHECK (previous_record_hash IS NULL OR previous_record_hash ~ '^sha256:[0-9a-f]{64}$')`, `written_at timestamptz NOT NULL DEFAULT now()`; create function `ledger.reject_mutation()` raising `ledger.ledger_record is append-only: <TG_OP> refused` with `ERRCODE = '42501'`; create trigger `ledger_record_no_update_delete` (`BEFORE UPDATE OR DELETE ... FOR EACH ROW`) and trigger `ledger_record_no_truncate` (`BEFORE TRUNCATE ... FOR EACH STATEMENT`); `GRANT SELECT, INSERT` on the table and `USAGE` on its sequence to the app role. Downgrade: drop the triggers, function and table, then the four schemas with `RESTRICT`
- [X] T018 [US2] Implement `make migrate` (`uv run alembic upgrade head`) and `make migrate-down` (prompt `Wipe ALL data in ADLC_ENV=<env>? type the env name to confirm`; on an exact match run `uv run alembic downgrade base`, otherwise exit 1 without changes) in `Makefile`, using a shared confirm helper script `deploy/confirm-env.sh`
- [X] T019 [US2] Run T014 and T015 and make them pass; keep the triggers as the enforcement and add no application-side guard (FR-011)

**Checkpoint**: migrations round-trip and the ledger refuses every mutation for both identities.

---

## Phase 4: User Story 3 - Configuration and secrets from the environment only (Priority: P1)

**Goal**: settings fail fast with named errors, secrets never appear in any output, and the repository holds only placeholders.

**Independent Test**: start `adlc-api` with one required setting removed → exit code 2 and a line naming it; with an invalid port → a line naming the expected form; no secret value is printed in either case.

### Tests for User Story 3 (write first, must fail) ⚠️

- [X] T020 [P] [US3] Write `tests/unit/test_settings.py`: for each required setting (`ADLC_ENV`, `ADLC_DB_HOST`, `ADLC_DB_APP_PASSWORD`, `ADLC_SESSION_SECRET`, `ADLC_ACCOUNTS_FILE`), removing it gives an error line `ADLC_<NAME>: missing; expected …` (SC-005); `ADLC_DB_PORT=abc` gives `ADLC_DB_PORT: invalid; expected integer 1-65535`; `ADLC_ENV=prod` is rejected; a short `ADLC_SESSION_SECRET` is rejected; the formatted output never contains any provided value; `repr(Settings)` and `model_dump_json()` contain no secret values
- [X] T021 [P] [US3] Write `tests/unit/test_env_example.py`: the keys in `.env.example` equal the `Settings` env names plus `POSTGRES_PASSWORD`; every secret key has the value `REPLACE_ME`
- [X] T022 [P] [US3] Write `tests/integration/test_startup_config.py`: running `python -m adlc.api` in a subprocess with `ADLC_SESSION_SECRET` unset exits with code 2 before binding a port, and stderr starts with `adlc: configuration error` and names the setting
- [X] T062 [P] [US3] Write `tests/integration/test_no_secrets_in_logs.py` (SC-008, FR-015): with distinctive values for `ADLC_DB_APP_PASSWORD`, `ADLC_DB_OWNER_PASSWORD` and `ADLC_SESSION_SECRET`, build the app against the test database, sign in, call `/auth/me` and `/health`, sign out, and shut down; assert that none of the secret values, the test password or the issued token appear in any captured log record or in stdout/stderr. Test ID T062 was added after analysis and runs with the other US3 tests

### Implementation for User Story 3

- [X] T023 [US3] Implement `format_settings_error(exc: ValidationError) -> str` in `src/adlc/config/errors.py`, producing the contracts/settings.md "Failure output" format (one line per field, `missing` or `invalid`, expected form, `(secret)` tag, never the value), and `load_settings_or_exit()`, which prints to stderr and calls `sys.exit(2)`
- [X] T024 [US3] Make `load_settings_or_exit(model)` generic over the settings class, and use it with `Settings` in `src/adlc/api/__main__.py` and `src/adlc/cli/account.py`, and with `DatabaseSettings` in `db/migrations/env.py`
- [X] T025 [P] [US3] Create `.env.example` with every key from contracts/settings.md, `REPLACE_ME` for secrets, the documented defaults for the rest, and the host-side values from "Host and container values" (`ADLC_DB_HOST=localhost`, `ADLC_ACCOUNTS_FILE=~/.config/adlc/accounts.dev.yaml` written as an absolute-path placeholder); confirm that `.env` is git-ignored

**Checkpoint**: misconfiguration is caught at startup with named, value-free messages.

---

## Phase 5: User Story 1 - One-command platform environment (Priority: P1) 🎯 MVP

**Goal**: `make up` / `down` / `status` / `reset` drive postgres, jaeger, migrate and api from `deploy/compose.yaml`; every service reports health; data survives restart.

**Independent Test**: from a clean checkout with `.env` filled in, `make up` returns with all services healthy in under 3 minutes and `/health` returns ok; `make down && make up` keeps the data; `make reset` with the typed confirmation empties it.

### Tests for User Story 1 (write first, must fail) ⚠️

- [X] T026 [P] [US1] Write `tests/integration/test_health.py`: with the database reachable, `GET /health` returns 200 `{"status":"ok","checks":{"database":"ok"}}` with no auth; with the database stopped it returns 503 with `checks.database = "unavailable"`; the body never contains host, user or password values
- [X] T027 [P] [US1] Write `tests/integration/test_database_wait.py`: `wait_for_database` against an unreachable port and a `2s` timeout raises `DatabaseUnavailable` within 5 s, with a message naming host and port but no password

### Implementation for User Story 1

- [X] T028 [US1] Implement `GET /health` in `src/adlc/api/routes/health.py` (database check runs `SELECT 1` through the app engine with a 2 s timeout) and register it in `create_app`
- [X] T029 [P] [US1] Write `deploy/api.Dockerfile`: `python:3.12-slim`, install uv, `uv sync --locked --no-dev`, copy `src`, `db`, `alembic.ini` and `adlc-specs`; run as a non-root user; `CMD ["adlc-api"]`
- [X] T030 [US1] Write `deploy/compose.yaml` with: `postgres` (image `postgres:16.x`, exact tag pinned; named volume `adlc-pgdata`; init dir mounted read-only; `pg_isready` healthcheck; host port `${ADLC_DB_PORT:-5432}`); `jaeger` (image `jaegertracing/jaeger:2.x`, exact tag pinned after checking the registry; OTLP 4318 internal; UI on `${ADLC_JAEGER_UI_PORT:-16686}`; healthcheck on the Jaeger health endpoint); `migrate` (api image, `command: alembic upgrade head`, `depends_on: postgres: service_healthy`, `restart: "no"`); `api` (api image, `depends_on: migrate: service_completed_successfully`, healthcheck on `/health`, host port `${ADLC_API_PORT:-8000}`, account file mounted read-only from `${ADLC_ACCOUNTS_FILE}` to `/run/adlc/accounts.yaml`). Postgres is published as `${ADLC_DB_PORT:-5432}:5432`. Per contracts/settings.md "Host and container values", the `environment:` block of `migrate` and `api` overrides `ADLC_DB_HOST: postgres` and `ADLC_DB_PORT: "5432"`, and `api` also overrides `ADLC_ACCOUNTS_FILE: /run/adlc/accounts.yaml`. All other values come from `.env`; no secret literal appears in the file
- [X] T031 [US1] Implement `make up` (`docker compose -f deploy/compose.yaml --env-file .env up -d --build --wait`), `make down` (`down` without `-v`), `make status` (`ps --format` table showing service and health) and `make reset` (`deploy/confirm-env.sh`, then `down -v`, then `make up`) in `Makefile`
- [X] T032 [US1] Bring the stack up locally and walk quickstart.md steps 2 and 9 (healthy in under 3 min; data survives `down`/`up`; reset empties it); fix whatever fails, then make T026 and T027 pass

**Checkpoint**: the MVP increment. The platform starts, reports health, persists data and resets on demand.

---

## Phase 6: User Story 4 - Local sign-in mapped to catalogue roles (Priority: P2)

**Goal**: sign-in through `IdentityProvider` with a local account file, roles validated against `adlc-specs/shared/roles.yaml`, deny by default on every other endpoint.

**Independent Test**: a configured account signs in and `/auth/me` returns its roles; an unknown account and a wrong password get identical 401 bodies; `/auth/me` without a token returns 401; after sign-out the token is refused.

### Tests for User Story 4 (write first, must fail) ⚠️

- [X] T033 [P] [US4] Write `tests/unit/test_password_hashing.py`: `hash_password` output matches `^scrypt\$32768\$8\$1\$[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+$`; `verify_password` is true for the right password and false for a wrong one; two hashes of the same password differ (salt); any value not starting with `scrypt$` is a placeholder and `verify_password` returns false
- [X] T034 [P] [US4] Write `tests/unit/test_role_catalogue.py`: loading `adlc-specs/shared/roles.yaml` yields exactly the 15 TDS §3 role ids; a duplicate id, a non-`snake_case` id or an empty description raises an error naming the entry
- [X] T035 [P] [US4] Write `tests/unit/test_accounts_file.py` (temp YAML files): a valid file loads; an unknown key, an unknown role, an empty `roles`, a duplicate `account_name` or an `account_name` not matching `^[a-z][a-z0-9._-]{1,39}$` each raise an error naming the account; a placeholder hash is a load error when `env=demo` and loads but is not sign-in-capable when `env=dev`
- [X] T036 [P] [US4] Write `tests/unit/test_session_tokens.py`: an issued token decodes to `account_name` and `session_id`; a tampered token, a token signed with another secret and a token older than the TTL (frozen clock) are refused; a revoked `session_id` is refused until its expiry and then dropped from the revocation set
- [X] T037 [P] [US4] Write `tests/integration/test_auth_api.py`: sign-in returns `token`, `token_type: bearer`, `expires_at` and `person`; `/auth/me` with the token returns the account's roles; the unknown-account and wrong-password responses are byte-identical 401 `{"detail":"invalid credentials"}`; `/auth/me` without a token or with a garbage token returns 401 `{"detail":"not authenticated"}`; after `/auth/sign-out` the token returns 401; captured logs contain `auth.sign_in` with `outcome=refused` and `outcome=success` but never the password, hash or token; a test-only route added to the app without an exemption returns 401 without a token (deny by default, FR-021)
- [X] T038 [P] [US4] Write `tests/unit/test_account_cli.py`: `adlc-account hash` with a patched `getpass` prints only a `scrypt$` line; mismatched confirmation exits 1; `adlc-account check` exits 0 on a valid file and 1 with account-named problems on an invalid one

### Implementation for User Story 4

- [X] T039 [P] [US4] Create `adlc-specs/shared/roles.yaml` with `schema_version: "1.0.0"` and the 15 roles of TDS §3 in order, each with `id` and `description` copied from the TDS role catalogue table (contracts/files.md)
- [X] T040 [P] [US4] Implement `src/adlc/identity/hashing.py`: `hash_password(password: str) -> str` (`hashlib.scrypt`, n=2**15, r=8, p=1, 16-byte salt, dklen 64, encoded `scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>`), `verify_password(password, encoded) -> bool` using `hmac.compare_digest`, and `is_placeholder(encoded) -> bool`
- [X] T041 [P] [US4] Implement `src/adlc/identity/catalogue.py`: `load_role_ids(path) -> frozenset[str]` with ruamel.yaml (safe loader) and the validation in T034
- [X] T042 [US4] Implement `src/adlc/identity/accounts.py`: an `Account` model (`account_name`, `display_name`, `roles: frozenset[str]`, `credential_hash`; extra keys forbidden) and `load_accounts(path, role_ids, env) -> dict[str, Account]` with the validation in T035
- [X] T043 [P] [US4] Implement `src/adlc/identity/sessions.py`: `SessionSigner` around `itsdangerous.URLSafeTimedSerializer` (salt `adlc.session`), `issue(account_name) -> (token, expires_at)`, `verify(token) -> SessionClaims`, and an in-process `RevocationSet` keyed by `session_id` with expiry pruning (research R-05)
- [X] T044 [US4] Implement `src/adlc/identity/protocol.py` (the `IdentityProvider` Protocol, `Person`, `SessionGrant`, and the exceptions `InvalidCredentials`, `NotAuthenticated`, `UnknownAccount` from contracts/identity-provider.md) and `src/adlc/identity/local.py` (`LocalIdentityProvider` implementing it: generic `InvalidCredentials` for unknown, wrong or placeholder; logs `auth.sign_in` with `account_name` and `outcome` only; `sign_out` is idempotent and logs `auth.sign_out`)
- [X] T045 [US4] Implement the deny-by-default auth dependency in `src/adlc/api/auth.py`: applied app-wide in `create_app`, with an explicit public allowlist of exactly `{"/health", "/auth/sign-in"}` (FR-021; the API docs routes `/docs` and `/openapi.json` stay behind sign-in); every other route requires `Authorization: Bearer`; errors map per contracts/identity-provider.md "Errors to HTTP"
- [X] T046 [US4] Implement `POST /auth/sign-in`, `POST /auth/sign-out` and `GET /auth/me` in `src/adlc/api/routes/auth.py` per contracts/platform-api.openapi.yaml; in `create_app`, build `LocalIdentityProvider` from `Settings` (`accounts_file`, `role_catalogue`, `session_secret`, `session_ttl`, `env`), so a bad account file stops startup with the account named
- [X] T047 [US4] Implement the Typer app in `src/adlc/cli/account.py`: `hash` (getpass twice, prints the hash only) and `check` (loads Settings, role catalogue and accounts; prints problems by account; exit 1 on any problem)
- [X] T048 [P] [US4] Create `deploy/accounts.example.yaml` per contracts/files.md (accounts `owner.business` with role `business_owner` and `coe.lead` with role `adlc_coe`, each `credential_hash: REPLACE_WITH_HASH`)

**Checkpoint**: people can sign in, roles come only from the catalogue, and every non-public route is protected.

---

## Phase 7: User Story 5 - Shared checks for developers and CI (Priority: P2)

**Goal**: `make check` runs lint, typecheck, test, migration-check and secret-scan; CI runs exactly `make check`.

**Independent Test**: `make check` passes on this codebase; a deliberate type error makes `make check` fail at `==> typecheck`.

### Tests for User Story 5 (write first, must fail) ⚠️

- [X] T049 [P] [US5] Write `tests/unit/test_build_contract.py`: `Makefile` defines every target in contracts/make-targets.md; `.github/workflows/ci.yml` has exactly one `run:` step that invokes `make` and it is `make check` (setup steps such as uv install excepted); no test or lint command appears in the workflow outside `make`

### Implementation for User Story 5

- [X] T050 [US5] Implement `scripts/migration_check.py`: start a fresh testcontainers `postgres:16` with the init script, then run upgrade head → downgrade base → upgrade head as owner, then assert the four schemas and both ledger triggers exist; exit 1 naming the failed step. Wire it to `make migration-check`
- [X] T051 [P] [US5] Create `.gitleaks.toml` that extends the default rules and allowlists only the documented placeholders (`REPLACE_ME`, `REPLACE_WITH_HASH`) and test fixture passwords under `tests/`; implement `make secret-scan` as `docker run --rm -v "$PWD:/repo" ghcr.io/gitleaks/gitleaks:<pinned v8 tag> dir /repo --config /repo/.gitleaks.toml --redact`
- [X] T052 [US5] Implement `make check` in `Makefile` to run `lint typecheck test migration-check secret-scan` in order, stopping at the first failure; set pytest coverage in `pyproject.toml` to `--cov=adlc.config --cov=adlc.identity --cov=adlc.db --cov-fail-under=80` (core modules, constitution IX), with a report for the whole `adlc` package shown but not gated
- [X] T053 [US5] Create `.github/workflows/ci.yml`: on `pull_request` and `push` to `main`; `ubuntu-latest`; checkout, `astral-sh/setup-uv` (pinned major), `make install`, `make check`

**Checkpoint**: one command gates every change, locally and in CI.

---

## Phase 8: User Story 6 - Trace collector ready for later features (Priority: P3)

**Goal**: every API request (except `/health`) produces an OpenTelemetry span exported over OTLP to Jaeger; tracing failure never affects requests.

**Independent Test**: a request to `/auth/me` appears in the Jaeger UI under service `adlc-api` within 30 s; with Jaeger stopped, requests still succeed and one WARNING is logged.

### Tests for User Story 6 (write first, must fail) ⚠️

- [X] T054 [P] [US6] Write `tests/unit/test_tracing.py` using `InMemorySpanExporter`: a request to a protected route creates one server span with `service.name = adlc-api`; `/health` creates no span; no span attribute key or value contains `authorization` or the bearer token; with an exporter that raises on export, the request still returns its normal status and a WARNING record is logged

### Implementation for User Story 6

- [X] T055 [US6] Implement `setup_tracing(app, settings, exporter=None)` in `src/adlc/observability/tracing.py`: `TracerProvider` with resource `service.name=adlc-api`, `BatchSpanProcessor` around an `OTLPSpanExporter(endpoint=f"{settings.otlp_endpoint}/v1/traces")` (or the injected exporter), `FastAPIInstrumentor.instrument_app(app, excluded_urls="/health")` with header capture off; a logging filter turns exporter errors into a single WARNING per failure burst. Call it from `create_app`
- [X] T056 [US6] Set `ADLC_OTLP_ENDPOINT=http://jaeger:4318` for `api` in `deploy/compose.yaml`, then walk quickstart.md step 7 (trace visible within 30 s; Jaeger stopped → requests still 200, WARNING logged)

**Checkpoint**: traces flow to Jaeger, ready for `run_id` tagging in 003–006.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T057 [P] Write `tests/unit/test_no_hardcoded_values.py` (constitution I, II): scan `src/adlc/**/*.py` and fail on any role id from `adlc-specs/shared/roles.yaml`, any terminal id matching `\bT[0-9]\b`, or any event name matching `\bT[0-9]\.[a-z]`
- [X] T058 [P] Write module READMEs: `src/adlc/config/README.md`, `src/adlc/db/README.md`, `src/adlc/identity/README.md` and `src/adlc/observability/README.md` (purpose, public interface, settings used)
- [X] T059 Write the root `README.md`: prerequisites, setup (quickstart.md steps 1–2), `make` targets, the two database identities, and the accepted MVP limits from the spec Assumptions (superuser can bypass immutability, sign-out not kept across API restart, no lockout, plain HTTP, reset allowed on `demo`)
- [X] T060 Update `claude.md`: replace "Run `make test`" with "Run `make check`", and add the location of the account file and the ADLC env selection
- [X] T061 Run `make check` and the full quickstart.md (steps 1–9) on a clean clone; record the results in `specs/001-platform-foundation/quickstart.md` under a "Validation run" note and fix anything that fails

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none
- **Foundational (Phase 2)**: after Setup; blocks every story
- **US2 (Phase 3)**: after Foundational
- **US3 (Phase 4)**: after Foundational; independent of US2 (it only touches config and the entry point)
- **US1 (Phase 5)**: after US2 (the migrate service runs its migrations) and US3 (startup validation)
- **US4 (Phase 6)**: after Foundational; its API tests need US1's `/health` wiring in `create_app`; the account-file mount it relies on is created in T030 (US1)
- **US5 (Phase 7)**: after US2 (migration-check reuses the migration); best done after US1–US4 so `make check` covers everything
- **US6 (Phase 8)**: after Foundational; T056 needs US1's compose file
- **Polish (Phase 9)**: after all stories

### Within each story

- Test tasks first; run them and see them fail
- Models and loaders → services and providers → routes and CLI → compose and Makefile wiring
- Each story ends at its checkpoint before the next starts

### Parallel Opportunities

- Setup: T002 and T005 alongside T003/T004
- Foundational: T006/T007, T009, T010 and T012 in parallel; T008 before T013
- US2: T014 and T015 together
- US3: T020, T021, T022 and T062 together; T025 alongside T023 (T062 passes only after US4 provides sign-in; until then it covers the start, health and shutdown part)
- US4: all six test tasks (T033–T038) together; then T039, T040, T041 and T043 together, followed by T042 → T044 → T045 → T046 → T047; T048 any time
- US3 and US2 can run in parallel with two developers; US6 can run alongside US4

## Parallel Example: User Story 4

```text
Tests together:   T033 hashing · T034 role catalogue · T035 accounts file · T036 sessions · T037 auth API · T038 CLI
Then together:    T039 roles.yaml · T040 hashing.py · T041 catalogue.py · T043 sessions.py · T048 accounts.example.yaml
Then in order:    T042 accounts.py → T044 provider → T045 auth dependency → T046 routes → T047 CLI
```

## Implementation Strategy

### MVP first

1. Phase 1 Setup → Phase 2 Foundational
2. US2 (migrations and ledger lock) → US3 (fail-fast config) → US1 (one-command environment)
3. **Stop and validate**: quickstart.md steps 2–5 and 9. This is the base feature 002 needs.

### Incremental delivery

4. US4 sign-in (needed by feature 007, not by 002–006)
5. US5 shared checks and CI (must be done before the feature's PR)
6. US6 tracing (needed by 003–006)
7. Polish and full quickstart run; then `/speckit-converge`

### Definition of done for this feature (build plan §9)

`make check` green, core coverage ≥ 80%, T057 passes (no hard-coded catalogue values), every
dependency licence is in plan.md, module READMEs are written, and quickstart.md is validated.

## Phase 10: Convergence

- [X] T063 CRITICAL: record the licences of build backend `hatchling` (MIT) and image dependencies `python:3.12-slim` (PSF-2.0) and `ghcr.io/astral-sh/uv` (MIT OR Apache-2.0) in the plan.md dependency table per Constitution VIII (missing)
- [X] T064 Show an ungated coverage report for the whole `adlc` package next to the gated core-module coverage in `Makefile`/`pyproject.toml` per tasks T052 (partial)
- [X] T065 After the branch is pushed to a Git remote, confirm `.github/workflows/ci.yml` runs `make check` green for the same commit that passes locally, and record the result in `specs/001-platform-foundation/quickstart.md` per SC-007 (partial)
