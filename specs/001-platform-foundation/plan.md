# Implementation Plan: Platform Foundation

**Branch**: `001-platform-foundation` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-platform-foundation/spec.md`

## Summary

Deliver the base every later feature builds on: a Compose environment (PostgreSQL 16, Jaeger,
platform API) driven by `make`; Alembic migrations creating the `spec`, `run`, `ledger` and
`events` schemas with a database-enforced append-only `ledger.ledger_record`; typed settings
that fail fast and never print secrets; local sign-in behind an `IdentityProvider` interface
with roles read from `adlc-specs/shared/roles.yaml`; OpenTelemetry request tracing to Jaeger;
and one set of `make` checks (ruff, mypy strict, pytest, migration round-trip, gitleaks) that
CI calls unchanged. Decisions and rejected alternatives are in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12 (uv-managed, single project, `src/adlc` package)

**Primary Dependencies**: FastAPI, Pydantic v2, pydantic-settings, uvicorn, SQLAlchemy 2,
Alembic, psycopg 3, ruamel.yaml, Typer, itsdangerous, OpenTelemetry SDK + OTLP exporter +
FastAPI instrumentation (licences in the table below)

**Storage**: PostgreSQL 16, one database `adlc`, schemas `spec`, `run`, `ledger`, `events`

**Testing**: pytest, pytest-cov, httpx (FastAPI test client), testcontainers-python
(PostgreSQL) for integration tests; ruff and mypy `--strict` as checks

**Target Platform**: Linux containers via Docker Compose (developer laptops on macOS/Linux and
the single demo host); CI on GitHub Actions `ubuntu-latest`

**Project Type**: web service + CLI tooling inside one Python package

**Performance Goals**: all services healthy ≤ 3 min after `make up` (SC-002); `/health`
answers in < 1 s; trace visible in Jaeger ≤ 30 s (SC-009); `make check` ≤ 10 min (SC-007)

**Constraints**: no secrets in repo, logs or traces (constitution XI); ledger rows immutable
for every DB identity (spec clarification 1); no terminal- or use-case-specific values in code
(constitution I, II); only OSI-licensed dependencies (constitution VIII)

**Scale/Scope**: one API process, one database, ≤ 20 local accounts, 15 catalogue roles

### Dependencies and licences (constitution VIII)

| Dependency | Use | Licence |
| --- | --- | --- |
| fastapi | Platform API | MIT |
| pydantic, pydantic-settings | Models, settings validation | MIT |
| uvicorn | ASGI server | BSD-3-Clause |
| sqlalchemy | DB access | MIT |
| alembic | Migrations | MIT |
| psycopg[binary] 3 | PostgreSQL driver | LGPL-3.0 (OSI; used as an unmodified library) |
| ruamel.yaml | Account file and role catalogue parsing (same parser as feature 002) | MIT |
| typer | `adlc-account` CLI | MIT |
| itsdangerous | Signed, timestamped session tokens | BSD-3-Clause |
| opentelemetry-api, -sdk, -exporter-otlp-proto-http, -instrumentation-fastapi | Tracing | Apache-2.0 |
| pytest, pytest-cov | Tests, coverage | MIT |
| httpx | API test client | BSD-3-Clause |
| testcontainers[postgres] | Real PostgreSQL in integration tests | Apache-2.0 |
| ruff, mypy | Lint, type check | MIT |
| PostgreSQL 16 (image `postgres:16`) | Database | PostgreSQL Licence |
| Jaeger v2 (image `jaegertracing/jaeger`) | Trace collector + viewer | Apache-2.0 |
| gitleaks (image `ghcr.io/gitleaks/gitleaks`) | Secret scan | MIT |
| GitHub Action `actions/checkout` | CI checkout | MIT |
| GitHub Action `astral-sh/setup-uv` | CI uv install | MIT |

Password hashing uses stdlib `hashlib.scrypt` (no extra dependency). Exact versions are pinned
in `pyproject.toml` / `uv.lock`, and image tags are pinned to exact versions in
`deploy/compose.yaml` at implementation time.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Article | How this plan complies | Status |
| --- | --- | --- |
| I Spec-driven | No terminal, control, event or threshold in code; roles read from `adlc-specs/shared/roles.yaml` | Pass |
| II Superset, not values | No use-case values introduced | Pass |
| III Agents build, humans decide | No outcome logic in this feature; identity establishes the human actor later features check | Pass (n/a) |
| IV Separation of duties | DB identities split (owner vs app); agent tokens come in 006 | Pass |
| V Evidence-first | `ledger.ledger_record` append-only via privileges + triggers for every identity; hash-chain columns present | Pass |
| VI Deterministic first | No judgement logic | Pass (n/a) |
| VII Interfaces at boundaries | `IdentityProvider` Protocol; DB behind SQLAlchemy engine factory; tracing via OTLP (vendor-neutral) | Pass |
| VIII Open source, Python first | Python 3.12, mypy strict; every dependency OSI-licensed and listed above | Pass |
| IX Test first for core | Ledger immutability, settings validation and sign-in tests written and failing before implementation | Pass |
| X Observable | Every API request traced; `run_activity` arrives with runs in 003/005 | Pass |
| XI Secure by default | Env-only secrets (`SecretStr`), gitleaks in checks, deny-by-default auth dependency, hashed credentials, generic sign-in failure | Pass |
| XII Simplicity | Stateless signed sessions, no identity server, no extra tables | Pass |
| XIII Naming | Schemas one lowercase word; `ledger_record`, `written_at`; kebab-case files/branches; `snake_case` settings fields | Pass |

**Post-design re-check (after Phase 1)**: Pass. The design adds no violations; the one
trade-off (in-memory sign-out revocation, research R-05) is recorded as post-MVP, not a
violation, so Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-platform-foundation/
├── plan.md              # This file
├── research.md          # Phase 0 decisions
├── data-model.md        # Phase 1: schemas, tables, roles, settings, accounts
├── quickstart.md        # Phase 1: validation run guide
├── contracts/
│   ├── platform-api.openapi.yaml   # /health, /auth/*
│   ├── identity-provider.md        # IdentityProvider interface contract
│   ├── settings.md                 # environment settings contract
│   ├── make-targets.md             # developer/CI command contract
│   └── files.md                    # roles.yaml and accounts file formats
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
pyproject.toml  uv.lock  Makefile  alembic.ini  .env.example  .gitleaks.toml  README.md
scripts/migration_check.py  # fresh-DB upgrade/downgrade/upgrade check (make migration-check)
src/adlc/
├── __init__.py
├── config/                 # settings.py (DatabaseSettings, Settings), durations.py, errors.py
├── db/                     # engine/session factory, connection wait
├── identity/               # IdentityProvider Protocol, LocalIdentityProvider,
│                           #   scrypt hashing, session tokens, role catalogue loader
├── observability/          # logging.py, tracing.py (non-blocking OTLP exporter)
├── api/                    # app.py factory, __main__.py, auth.py dependency,
│                           #   routes/health.py, routes/auth.py
├── cli/                    # Typer app: `adlc-account hash`, `adlc-account check`
├── spec_toolkit/  orchestration/  policy/  ledger/  agents/  ui/   # README placeholders
adlc-specs/
├── shared/roles.yaml       # 15 roles, TDS §3
├── terminals/  playbooks/  checklists/  schema/                     # README placeholders (002)
db/migrations/              # Alembic env.py + versions/0001_baseline.py
deploy/
├── compose.yaml            # postgres, jaeger, migrate (one-shot), api
├── api.Dockerfile
├── confirm-env.sh          # typed env-name confirmation for reset / migrate-down
├── postgres/init/01-roles.sh   # creates owner + app login roles from env
└── accounts.example.yaml   # placeholder hashes only
mcp_servers/  pilot/        # README placeholders
tests/
├── unit/                   # settings, hashing, tokens, role catalogue, accounts file
├── integration/            # migrations round-trip, ledger immutability, API auth, health
└── scenario/               # README placeholder (014)
.github/workflows/ci.yml    # calls make targets only
```

**Structure Decision**: one Python package `adlc` with modules per layer as in build plan §5.
`config`, `db`, `identity`, `observability` and `cli` are cross-cutting modules added by this
feature under `src/adlc/`; the layer modules for later features are README placeholders.

## Complexity Tracking

No constitution violations; nothing to justify.
