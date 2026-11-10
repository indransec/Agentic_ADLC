# Agentic ADLC platform

The platform drives an agentic use case through lifecycle terminals T0–T9: agents build, and humans decide. It is built feature by feature with GitHub Spec Kit. See `docs/build-plan.md` for the build order, and `specs/<nnn>-<feature>/` for each feature's spec, plan and tasks.

| Path | Holds |
| --- | --- |
| `docs/` | Solution architecture (SA), Terminal Design Specification (TDS), build plan |
| `specs/` | Spec Kit feature specs (Markdown). Owned by Spec Kit. |
| `adlc-specs/` | ADLC terminal specs and shared catalogues (runtime YAML), e.g. `shared/roles.yaml` |
| `src/adlc/` | Platform code, one module per layer |
| `db/migrations/` | Alembic migrations |
| `deploy/` | Compose environment, API image, Postgres init, example account file |
| `tests/` | Unit, integration (Docker) and scenario tests |

## Prerequisites

Docker with Compose v2 (running), [uv](https://docs.astral.sh/uv/), GNU make and git. Python 3.12 is installed by uv.

## Set up and run

```bash
make install
cp .env.example .env            # replace every REPLACE_ME (use long random values)
mkdir -p ~/.config/adlc
cp deploy/accounts.example.yaml ~/.config/adlc/accounts.dev.yaml
# set ADLC_ACCOUNTS_FILE in .env to the absolute path of that file, then for each account:
uv run adlc-account hash        # paste the output into credential_hash
set -a; source .env; set +a; uv run adlc-account check
make up                         # returns when every service is healthy
curl -s localhost:${ADLC_API_PORT:-8000}/health
```

The Jaeger UI is at `http://localhost:16686` (service `adlc-api`). If a port is already taken, change `ADLC_API_PORT`, `ADLC_DB_PORT` or `ADLC_JAEGER_UI_PORT` in `.env`.

## Commands

| Command | What it does |
| --- | --- |
| `make up` / `make down` / `make status` | Start (migrate → register specs → API, waits until healthy), stop (data kept), show service health |
| `make reset` | Wipe all data after you type the `ADLC_ENV` name, then start again |
| `make migrate` / `make migrate-down` | Apply migrations / roll back to empty (asks for the same confirmation) |
| `make spec-validate` | Validate `adlc-specs/` at L1–L5 (L5 compares with `origin/main`) |
| `make spec-register` | Register validated specs and catalogues into the `.env` data store |
| `make check` | lint → typecheck → spec-validate → test → migration-check → secret-scan (what CI runs) |

Terminal specs, catalogues, checklists and playbooks live in `adlc-specs/`; `adlc-specs/CONVERSION.md`
records how they were converted from the TDS.

Run `make check` before calling a task done.

## Data store identities

- `adlc_owner` owns the schemas and is used only by migrations.
- `adlc_app` is used by running services and can only read and insert ledger records.
- `ledger.ledger_record` refuses UPDATE, DELETE and TRUNCATE for every identity.
- The container superuser (`POSTGRES_PASSWORD`) is used only once, to create the two identities.

## Accepted MVP limits

These are recorded in `specs/001-platform-foundation/spec.md` (Assumptions).

- A PostgreSQL superuser can bypass ledger immutability. Signed evidence and write-once storage come later.
- A sign-out is not remembered after the API restarts; the session lasts at most `ADLC_SESSION_TTL`.
- There is no lockout after failed sign-ins, but every failure is logged.
- Traffic is plain HTTP on the single private demo network.
- `make reset` works on `demo` too, after the typed confirmation, for rehearsals.
