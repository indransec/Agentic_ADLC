# Implementation Plan: ADO Simulator API

**Branch**: `015-ado-sim-api` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/015-ado-sim-api/spec.md` (Gate 1 approved 2026-11-20)

## Summary

The ADO simulator is a separate uv project, `ado_sim/`, that never imports the platform and is
never imported by it. This feature builds its ADO-compatible REST API subset (version 7.1):

- **Work items:** create, get, list, batch and update, with JSON Patch and `test /rev` for
  optimistic concurrency.
- **History:** updates and revisions, every change kept with who made it.
- **Queries:** a WIQL subset, refusing anything outside it.
- **Links and comments:** parent/child and predecessor/successor links; comments.
- **Process:** work item types, states and fields, and the area tree.
- **Identities:** personal access tokens.

The work item process (Agile, with the Epic's states being the terminal stages), area paths and
identities come from a seed file; tokens are issued and revoked by an operator command and stored
only as keyed hashes. Data lives in the simulator's own SQLite file. The contract is written from
Microsoft's 7.1 reference (research R-01), committed as `contract/openapi.json`, with request and
response fixtures that feature 016 will reuse, and a list of known differences from ADO. The
simulator runs as a compose service and as a process in `make local`; `make ado-sim-check` joins
`make check`.

## Technical Context

**Language/Version**: Python 3.12, uv, ruff, mypy strict, pytest; `ado_sim/` has its own
`pyproject.toml` and `uv.lock` (as `pilot/`).

**Primary Dependencies**: FastAPI 0.162.2, uvicorn 0.54.0, pydantic 2.14.3, ruamel.yaml 0.19.1,
the OpenTelemetry API, SDK and OTLP exporter 1.45.2 (optional traces); tests: httpx 0.28.1,
pytest, pytest-cov. All already pinned in the platform or the pilot; no new licence (research,
"Dependencies and licences").

**Storage**: one SQLite file through the standard library `sqlite3` (WAL, foreign keys,
`BEGIN IMMEDIATE` writes, ISO UTC text times); numbered SQL migrations (research R-04;
[data-model.md](data-model.md)).

**Testing**:
- **Unit (test first, constitution IX):**
  - the patch applier;
  - WIQL tokenizer, parser and compiler;
  - revision and update recording;
  - relation rules (second parent, cycle, self-link);
  - the token HMAC and auth parsing;
  - seed file validation.
- **API** (FastAPI test client): every operation, including its refusals.
- **Contract:**
  - fixture replay against a freshly seeded simulator (SC-001);
  - the served OpenAPI document equals the committed one.
- **Properties:**
  - polling completeness over 1,000 changes (SC-002);
  - 20 concurrent conditional updates (SC-003);
  - timing with 5,000 items (SC-004);
  - restart (SC-005);
  - seed time (SC-006);
  - token scan of responses, logs, seed and fixtures (SC-007).
- **Boundary:**
  - `ado_sim` imports nothing from `adlc`;
  - `adlc` imports nothing from `ado_sim` (SC-008, in both projects' test suites).

**Target Platform**: compose service `ado-sim` (`deploy/ado-sim.Dockerfile`, image
`adlc-ado-sim:0.1.0`, volume `ado-sim-data`, port 8600, platform network); without Docker, a
process in `deploy/Procfile.local` with data in `data/local/ado_sim/`.

**Project Type**: web service (REST API) with operator commands.

**Performance Goals**: 95% of single-item reads, updates and supported queries within 1 s with
5,000 items (SC-004); seed or reset under 1 minute (SC-006).

**Constraints**:
- no shared code, data or settings with the platform;
- no lifecycle, policy or decision-rights logic;
- tokens never stored or logged in clear;
- unsupported operations and WIQL constructs refused, never half-answered.
- requests bounded (field and comment 1 MB, 500 patch operations, 32 KB queries, 5 MB bodies);
- a link change is one transaction across both items.

**Scale/Scope**: one organisation and project, a few thousand work items, about 10 identities,
one sync client plus a few people.

## Constitution Check

*Gate: passes before Phase 0; re-checked after Phase 1 design.*

| Article | Check | Result |
| --- | --- | --- |
| I Spec-driven lifecycle | No lifecycle behaviour in the simulator; the terminal stages are seed data | Pass |
| II Superset, not values | Process, stages and fields in `seed/demo.yaml`; no terminal or use-case value in code | Pass |
| III Agents build, humans decide | No decision logic in the simulator; every change attributed to its identity for the platform to check (016) | Pass |
| IV Separation of duties | Not applicable (no agent tools here); every request authenticated | Pass |
| V Evidence-first | Append-only updates and revisions (triggers), every change with changer and time | Pass |
| VI Deterministic before judgement | No model or judgement anywhere | Pass |
| VII Interfaces at every boundary | Separate project, own data store, published contract; boundary tests both ways (constitution 1.2.0 proposed) | Pass |
| VIII Open source, Python first | Python 3.12, mypy strict, ruff; every dependency listed with its licence, all OSI and already in use | Pass |
| IX Test first for the core | Unit tests written first for patch, WIQL, history, relations, tokens; coverage ≥ 80% | Pass |
| X Observable by default | Request logs; optional OTLP traces to Phoenix | Pass |
| XI Secure by default | Tokens keyed-hashed, issued by command, never logged or committed; `401` reveals nothing; no secrets in the repository | Pass |
| XII Simplicity for the MVP | Only the subset 016–018 need; deletes, attachments, iterations, webhooks out; supports D-12 and D-13 through 016 | Pass |
| XIII Naming | Annex A for files, settings and branches; ADO names (`System.*`, `Custom.*`) are the external contract | Pass |

Post-design re-check: Pass, with no violations. One note, recorded for review: the contract
source changed from a vendored specification to our own description written from the reference,
because the specification repository no longer exists (research R-01).

## Project Structure

### Documentation (this feature)

```text
specs/015-ado-sim-api/
├── spec.md
├── plan.md              # this file
├── research.md          # R-01 … R-13, dependencies and licences
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── operations.md    # the REST subset, with reference pages
│   ├── wiql.md          # the WIQL subset
│   └── cli-settings-seed.md
├── checklists/
│   └── requirements.md
└── tasks.md             # /speckit-tasks (Gate 3)
```

### Source code

```text
ado_sim/                          # own uv project; imports nothing from adlc
├── pyproject.toml, uv.lock, README.md
├── seed/demo.yaml                # process, areas, identities (no tokens)
├── contract/
│   ├── openapi.json              # committed, equals the served document
│   ├── differences.md            # known differences from real ADO
│   └── fixtures/<operation>/<case>.json
├── src/ado_sim/
│   ├── __main__.py, cli.py       # ado-sim migrate | seed | reset | token | serve | export-openapi
│   ├── settings.py               # ADO_SIM_* settings
│   ├── db.py                     # connection set-up, transactions, migrations runner
│   ├── migrations/0001_initial.sql
│   ├── seed.py                   # seed file load and validation
│   ├── auth.py                   # token hashing, request authentication
│   ├── patch.py                  # ADO JSON Patch applier
│   ├── workitems.py              # create, get, update, history, relations
│   ├── wiql.py                   # tokenizer, parser, SQL compiler
│   ├── comments.py
│   ├── process.py                # types, states, fields, area tree, identities
│   ├── errors.py                 # ADO error bodies and status codes
│   ├── app.py                    # FastAPI app and routes
│   └── observability.py          # request logs, optional traces
└── tests/
    ├── unit/                     # patch, wiql, history, relations, auth, seed
    ├── api/                      # every operation through the test client
    ├── contract/                 # fixture replay, OpenAPI equality
    └── properties/               # SC-002 … SC-007, boundary

deploy/ado-sim.Dockerfile         # new image
deploy/compose.yaml               # + ado-sim service and ado-sim-data volume
deploy/Procfile.local, deploy/local.env   # + ado-sim process and its settings
Makefile                          # + ado-sim-check (in check), ado-sim targets in local-setup
tests/unit/test_ado_sim_boundary.py   # the platform imports nothing from ado_sim
```

**Structure Decision**: a separate uv project at the repository root, mirroring `pilot/`, because
the simulator must share nothing with the platform and later grows its own UI (017, 018).

## Complexity Tracking

No constitution violations to justify.
