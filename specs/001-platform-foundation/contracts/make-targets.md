# Contract: Developer and CI commands

`make` is the single entry point (FR-022, FR-023). CI runs `make check` and nothing else.
Every target exits non-zero on failure and prints the name of the failing step.

| Target | Does | Needs |
| --- | --- | --- |
| `make install` | `uv sync` (locked) | uv |
| `make up` | Start postgres, jaeger, migrate, api; wait until healthy | Docker, `.env` |
| `make down` | Stop services; keep data volume | Docker |
| `make status` | Show each service with its health | Docker |
| `make reset` | Prompt `Wipe ALL data in ADLC_ENV=<env>? type the env name to confirm`; remove the data volume; `make up` | Docker, `.env` |
| `make migrate` | `alembic upgrade head` as `adlc_owner` against `ADLC_DB_*` | running postgres |
| `make migrate-down` | `alembic downgrade base` with the same confirmation as reset | running postgres |
| `make lint` | `ruff check` + `ruff format --check` | uv |
| `make typecheck` | `mypy --strict src tests` | uv |
| `make test` | `pytest` unit + integration with coverage report (core modules ≥ 80%) | uv, Docker (testcontainers) |
| `make migration-check` | Fresh PostgreSQL: upgrade head → downgrade base → upgrade head; assert schemas and ledger triggers | uv, Docker |
| `make secret-scan` | gitleaks over the working tree with `.gitleaks.toml` | Docker |
| `make spec-validate` | `adlc-spec validate adlc-specs` at L1–L5, L5 against `ADLC_SPEC_BASELINE_REF` (default `origin/main`); added by feature 002 | uv, git |
| `make spec-register` | `adlc-spec register adlc-specs` into the `.env` data store; added by feature 002 | running postgres |
| `make check` | lint → typecheck → spec-validate → test → migration-check → secret-scan | all of the above |

## CLI: `adlc-account`

| Command | Does |
| --- | --- |
| `adlc-account hash` | Prompts for a password twice (no echo) and prints the `scrypt$…` hash only |
| `adlc-account check` | Validates the file at `ADLC_ACCOUNTS_FILE` against the role catalogue; lists problems by account name; exit 1 on any problem; in `demo`, placeholders count as problems |
