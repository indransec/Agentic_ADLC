# Research: Platform Foundation (001)

Each entry records a decision, why it was made, and what was rejected. All Technical Context
items are resolved; nothing remains marked NEEDS CLARIFICATION.

## R-01 Environment runtime and command entry point

- **Decision**: Docker Compose file `deploy/compose.yaml` with services `postgres`, `jaeger`,
  `migrate` (one-shot, runs `alembic upgrade head` as the schema owner) and `api`. `api`
  depends on `migrate` completing successfully, and `migrate` depends on `postgres` being
  healthy. `make up` runs `docker compose up -d --wait`, so it returns only when every service
  is healthy or fails naming the unhealthy one. PostgreSQL data lives in a named volume, so
  `make down` keeps it; `make reset` asks for confirmation, prints `ADLC_ENV`, then removes the
  volume and runs `make up`.
- **Rationale**: SA §15 and build plan §4 (Compose on one host); `--wait` gives FR-003 and
  SC-002 without custom polling; the one-shot migrate service keeps the schema in step with
  the code on every start.
- **Alternatives**: a shell script instead of make (no standard target list for CI);
  running migrations inside API startup (couples the API to the owner credentials, against
  FR-010).

## R-02 Two database identities and how they are created

- **Decision**: the container superuser (`POSTGRES_USER`) is infrastructure-only. An init
  script `deploy/postgres/init/01-roles.sh` (run once on first volume creation) creates two
  login roles from environment settings: `adlc_owner` (owns database objects, used only by
  migrations) and `adlc_app` (runtime). Migrations grant `adlc_app` `USAGE` on the four
  schemas and explicit per-table privileges, never default privileges. Integration tests run
  the same init script against a testcontainers PostgreSQL.
- **Rationale**: FR-010; explicit grants per table keep the access rules readable in each
  migration; one init script means tests and Compose use identical role setup.
- **Alternatives**: creating roles inside Alembic (needs `CREATEROLE` on the owner, which
  widens its rights); a single role with application-level checks (fails FR-011).

## R-03 Ledger immutability for every identity

- **Decision**: in the baseline migration, `adlc_app` gets only `SELECT, INSERT` on
  `ledger.ledger_record`. Two triggers apply to every identity, including the owner: a
  `BEFORE UPDATE OR DELETE ... FOR EACH ROW` trigger and a `BEFORE TRUNCATE ... FOR EACH
  STATEMENT` trigger, both calling `ledger.reject_mutation()`, which raises an exception
  naming the table. The downgrade drops the table, triggers and function, which is how
  reset and full rollback remove ledger data (spec clarification 1).
- **Rationale**: privileges alone do not stop the table owner; triggers do. `DROP TABLE` is
  unaffected by row and truncate triggers, so rollback still works.
- **Known limit**: a PostgreSQL superuser can disable triggers. The superuser is an
  infrastructure credential not used by any platform service; this is documented in the
  README and SA §11 target state (signed evidence, WORM) covers it later.
- **Alternatives**: rules (`CREATE RULE ... DO INSTEAD NOTHING`) silently ignore changes
  instead of refusing them, which fails the "refused" acceptance; row-level security does not
  apply to the table owner by default.

## R-04 Credential hashing

- **Decision**: stdlib `hashlib.scrypt` (n=2^15, r=8, p=1, 16-byte random salt, 64-byte key),
  stored as `scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>`. Compare with
  `hmac.compare_digest`. `adlc-account hash` reads the password twice through `getpass` and
  prints only the encoded hash. The placeholder value in the example file is
  `REPLACE_WITH_HASH`; any value not starting with `scrypt$` is treated as a placeholder.
- **Rationale**: memory-hard KDF with no new dependency (constitution XII); the encoded form
  carries its parameters so they can be raised later.
- **Alternatives**: argon2-cffi (MIT, stronger, but an extra compiled dependency for a
  ≤ 20-account demo); bcrypt (72-byte input limit).

## R-05 Session tokens and sign-out

- **Decision**: stateless signed tokens using `itsdangerous.URLSafeTimedSerializer`, keyed by
  `ADLC_SESSION_SECRET`, payload `{account_name, session_id}`, max age `ADLC_SESSION_TTL`
  (default `8h`). Sent as `Authorization: Bearer <token>` (the Streamlit UI in 007 calls the
  API server-side, so a header suits it better than a browser cookie). Sign-out adds the
  `session_id` to an in-process revocation set that holds entries until their expiry. Roles
  are re-read from the account file on every request, so a role removed from the file takes
  effect immediately.
- **Rationale**: no session table is needed, which keeps this feature inside its four-schema
  scope; itsdangerous is small, maintained and BSD-licensed, which is safer than hand-rolled
  HMAC.
- **Trade-off (post-MVP)**: revocations are lost on API restart, so a signed-out token stays
  valid until it expires (≤ 8 h). Acceptable for one API process on a demo host; moving to
  OIDC (SA §11 target) removes it. Recorded here instead of being built (constitution XII).
- **Alternatives**: server-side session table (needs a fifth schema or a misplaced table);
  JWT library (more surface than needed for one issuer and one audience).

## R-06 Settings and fail-fast validation

- **Decision**: one `Settings` class (pydantic-settings) with prefix `ADLC_`. Secrets are
  `SecretStr`. Duration settings use `<int><unit>` with units `s`, `min`, `h`, `d` (for
  example `8h`, `90s`). The bare `m` is rejected because TDS Annex B.1 uses `m` for months.
  See [contracts/settings.md](contracts/settings.md). On a
  `ValidationError`, the entry point prints one line per failing field (`ADLC_<FIELD>:
  <problem>; expected <form>`) and exits with code 2 before uvicorn binds a port. Values are
  never echoed. The contract is in [contracts/settings.md](contracts/settings.md).
- **Rationale**: FR-013, FR-014, FR-015; one place lists every setting, so the example file
  and the docs cannot drift (a unit test checks `.env.example` keys against the model).
- **Alternatives**: dynaconf or environs (extra concepts for no gain).

## R-07 Role catalogue and account file

- **Decision**: `adlc-specs/shared/roles.yaml` holds a list of `{id, description}` for the 15
  roles in TDS §3 (`schema_version: "1.0.0"`). The identity module loads role ids from that
  file at startup; it contains no role names in code. The account file (path from
  `ADLC_ACCOUNTS_FILE`) lists `{account_name, display_name, roles[], credential_hash}`.
  Startup fails on an unknown role, a duplicate account name, an empty role list, or (when
  `ADLC_ENV=demo`) any placeholder hash. Formats are in [contracts/files.md](contracts/files.md).
- **Rationale**: FR-018, FR-019, FR-028; feature 002 adds JSON Schema validation for the same
  file without changing its shape.

## R-08 Tracing

- **Decision**: OpenTelemetry SDK with `BatchSpanProcessor` and the OTLP/HTTP exporter to
  `ADLC_OTLP_ENDPOINT` (Jaeger v2 receives OTLP on 4318; UI on 16686).
  `FastAPIInstrumentor` traces each request; service name is `adlc-api`. The batch processor
  exports off the request path, and exporter errors are logged at WARNING by a logging filter,
  so a stopped Jaeger never fails or slows requests (FR-026). Health-check requests are
  excluded from tracing to keep the viewer readable. Request and response headers are not
  captured as span attributes (the instrumentation's header capture stays off), and the
  access log format omits headers, so the `Authorization` token is never recorded (FR-015).
- **Rationale**: constitution X; OTLP keeps Jaeger swappable for Langfuse or Tempo by setting
  only (user decision: Jaeger for MVP). Jaeger v1 all-in-one reached end of life, so v2 is used.
- **Alternatives**: Langfuse (heavier: ClickHouse and Redis), console exporter (no viewer).

## R-09 Shared checks and CI

- **Decision**: `make check` runs, in order: `lint` (ruff check + ruff format --check),
  `typecheck` (mypy --strict on `src` and `tests`), `test` (pytest unit + integration with
  coverage; integration uses testcontainers), `migration-check` (on a fresh testcontainers
  PostgreSQL: upgrade head → downgrade base → upgrade head, then assert the four schemas and
  the ledger triggers exist) and `secret-scan` (gitleaks container over the working tree with
  `.gitleaks.toml` allowing only the documented placeholders). `.github/workflows/ci.yml`
  installs uv, then calls `make check`; the runner's Docker serves testcontainers and gitleaks.
- **Rationale**: FR-022 to FR-024; one command list means CI and developers cannot diverge.
- **Alternatives**: a CI Postgres service container (a second way to get a database, used
  only in CI, which FR-023 forbids); pre-commit as the runner (useful later, not a CI contract).

## R-10 Waiting for the database and health

- **Decision**: at startup the API retries a `SELECT 1` as `adlc_app` for up to
  `ADLC_DB_CONNECT_TIMEOUT` (default `60s`), then exits with a message
  naming the host and port. `GET /health` returns `200 {"status": "ok", "checks": {"database":
  "ok"}}` or `503` with the failing check named; it never includes setting values. Compose
  healthchecks: `pg_isready` for PostgreSQL, the Jaeger admin health endpoint for Jaeger, and
  `/health` for the API.
- **Rationale**: edge case "data store not ready" and FR-003.

## R-12 MVP security limits accepted at Gate 2

- **Decision** (2026-11-09, Gate 2): no sign-in lockout, but every failure is logged
  (FR-021a); plain HTTP on the private demo network; reset and rollback allowed in `dev` and
  `demo` behind the typed environment-name confirmation; the superuser credential is used
  only by the init script; sign-out is not remembered across API restarts (R-05). All five
  are recorded as spec assumptions with their post-MVP path.
- **Rationale**: constitution XII; the demo runs on synthetic data on one private host.

## R-11 Port conflicts and repeated `make up`

- **Decision**: host ports come from settings (`ADLC_API_PORT`, `ADLC_DB_PORT`,
  `ADLC_JAEGER_UI_PORT`) with defaults 8000, 5432, 16686. Compose reports a bind failure
  naming the service and port; `make up` on a running stack is a no-op that reports state
  (Compose is idempotent).
- **Rationale**: edge cases on ports and repeated start; no custom code needed.
