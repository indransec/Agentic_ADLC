# Implementation Plan: Engagement Layer (board ↔ platform)

**Branch**: `016-engagement-layer` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/016-engagement-layer/spec.md` (Gate 1 approved
2026-11-20)

## Summary

A new platform package, `src/adlc/engagement/`, connects the platform to a tracker through a
board-neutral `BoardAdapter` port. One ADO REST 7.1 adapter talks to the feature 015 simulator as
it would to `dev.azure.com`; an in-memory `FakeBoard` implements the same port for tests. A new
process, `adlc-board run`, does two things:

- **Outbound projection** (R-03): for each use case whose history changed, compute the desired
  board state (Epic in its terminal's column with the run state as sub-stage, a run item per run,
  a clarification item per round) from the platform's tables and write only the differences, with
  the outbox's retry schedule and dead-letter rule, after the platform's transactions commit.
- **Inbound sync** (R-04–R-07): poll the board's revisions from a watermark using the simulator's
  `asOf` guarantee, classify each person's update with pure rules, and apply each request through
  the existing `OrchestratorService` operations as the mapped person, exactly once; refusals and
  platform-field edits are reverted on the board with the reason.

Everything tracker-specific is in `adlc-specs/tracker_mapping.yaml`, validated by the spec toolkit
(V-32–V-36) and checked against the board at start. Reconciliation (CoE, CLI and API) is the
projector without its cache (R-08). Sync state lives in new tables (one migration); sync health is
served by the API and CLI for the console of 019. A contract suite runs both adapters, the ADO one
against a simulator the tests start from this repository.

## Technical Context

**Language/Version**: Python 3.12, the platform's uv project, ruff, mypy strict, pytest.

**Primary Dependencies**: httpx 0.28 (the adapter's HTTP client), pydantic and pydantic-settings,
SQLAlchemy Core and Alembic, ruamel.yaml, OpenTelemetry; tests: respx, hypothesis. All already
locked; no new dependency (research, "Dependencies and licences").

**Storage**: the platform's SQLite file (`ADLC_DB_PATH`), migration `0002_board.py`
([data-model.md](data-model.md)); append-only triggers on history tables.

**Testing**:
- **Unit (test first, constitution IX):**
  - mapping schema and rules V-32–V-36 (negative fixtures as in 002);
  - desired-state computation and diffing;
  - change classification (`classify`);
  - decision-input parsing (`read_inputs`), fields, comment lines, precedence;
  - answer splitting;
  - exactly-once bookkeeping and crash recovery (R-07);
  - identity mapping and the accounts file's `board_identity`.
- **Service** (FakeBoard + the platform's test harness): every user story against real
  `OrchestratorService`, ledger and policy.
- **Contract** (`tests/contract/board/`): the port suite on FakeBoard and on the ADO adapter
  against a simulator started by a session fixture; the ADO readers decode every 015 fixture.
- **Properties:** 500 changes with overlapping polls and a restart (SC-003); outage and
  recovery (SC-005); reconciliation of 50 use cases (SC-006); full lifecycle from the board
  (SC-007); latency measured on FakeBoard with a 10 s interval (SC-001, SC-002).
- **Scans:** no tracker names in code (extended `test_no_hardcoded_values.py`); boundary both ways.

**Target Platform**: the demo host (compose) and a laptop without Docker (`make local`).

**Project Type**: a new package and process inside the platform's web service.

**Performance Goals**: a board decision applied and shown within 30 s (SC-001); a platform change
on the board within 15 s (SC-002); reconciliation of 50 use cases under 1 minute (SC-006).

**Constraints**: the platform never waits for the board (no HTTP inside a platform transaction);
no tracker value in code; no token or field value in logs; the inbox keeps working.

**Scale/Scope**: the demo: tens of use cases, ten terminals, a handful of people; one board
project.

## Constitution Check

*Gate before Phase 0; re-checked after Phase 1.*

| Article | How this plan complies |
| --- | --- |
| I Spec-driven | the board model is data in `adlc-specs/tracker_mapping.yaml`, validated with the terminal specs; terminal ids appear only there |
| II Superset, not values | tracker names come from the mapping; the hard-coded-values scan is extended to them |
| III Agents build, humans decide | only people's board changes become decisions; the service account never decides; agents do not touch the board |
| IV Separation of duties | decision rights, waiver proposer ≠ approver and every other rule stay in the existing services, checked as the mapped person |
| V Evidence-first | commands write the same activity, decision log and ledger records as the inbox, with the board item as source; the board is updated only after the platform commits |
| VI Deterministic first | classification, input parsing and desired state are pure, deterministic functions |
| VII Interfaces | `BoardAdapter` port; `FakeBoard` and the ADO adapter pass one contract suite; the platform imports nothing from `ado_sim` |
| VIII Open source, Python | no new dependency |
| IX Test first | the core modules above are written test first |
| X Observable | spans and logs per poll, change, command, write and reconciliation; sync health |
| XI Secure | the token is a secret setting, never logged; unmapped board users are refused before any right is checked; history tables append-only |
| XII Simplicity | polling only, manual reconciliation, state-based projection without new events, one process |
| XIII Naming | tables `board_*` and `inbound_*`, package `engagement`, SA Annex A conventions |

**Result: pass**, with one spec wording change (R-03, Complexity Tracking).

## Project Structure

### Documentation (this feature)

```text
specs/016-engagement-layer/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/
│   ├── board-port.md
│   ├── tracker-mapping.md
│   ├── inbound-rules.md
│   └── api-cli-settings.md
└── checklists/
```

### Source Code (repository root)

```text
src/adlc/engagement/
├── __init__.py, README.md
├── model.py          board-neutral types
├── port.py           BoardAdapter protocol and errors
├── ado.py            the ADO REST 7.1 adapter (httpx)
├── fake.py           FakeBoard (in-memory, same port)
├── mapping.py        load and query tracker_mapping.yaml; board check
├── identities.py     board identity ↔ account (accounts file, roles)
├── desired.py        desired board state of a use case (pure)
├── projector.py      dirty use cases, diff, write, retries, dead letters
├── classify.py       a board update → actions (pure)
├── inputs.py         decision inputs from fields and comment lines (pure)
├── inbound.py        poll, claim, apply through OrchestratorService, reply
├── reconcile.py      reconciliation and its report
├── health.py         sync health from the tables
├── store.py          all SQL of the board tables
├── worker.py         the adlc-board run loop and /health
└── cli.py            adlc-board commands
src/adlc/api/routes/board.py         GET /board/health, reconciliations, requeue
src/adlc/config/settings.py          BoardSettings
src/adlc/identity/accounts.py        optional board_identity
src/adlc/orchestration/service.py    optional `source` recorded in run activity
src/adlc/spec_toolkit/               optional top-level tracker_mapping.yaml; rules V-32..V-36
adlc-specs/tracker_mapping.yaml
adlc-specs/schema/catalogues/tracker_mapping.schema.json
db/migrations/versions/0002_board.py
ado_sim/seed/demo.yaml               + RootCause, Reason, ReworkTarget, Values, EvidenceLink
deploy/compose.yaml, Procfile.local, local.env, README.md; .env.example; docs/run-without-docker.md
tests/unit/engagement/, tests/integration/engagement/, tests/contract/board/
```

**Structure Decision**: one new package in the existing platform project, one new process using
the platform image; the simulator changes only its seed data.

## Complexity Tracking

| Deviation | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| FR-007 said "through the platform's existing outbox"; the projector keeps its own per-use-case delivery state with the outbox's retry schedule and dead-letter rule | the outbox delivers inside the router's write transaction; a board HTTP call there would hold SQLite's write lock during board latency or outages, and run state changes are not outbox events (R-03) | adding an event per transition and a board subscriber still calls HTTP inside the delivery transaction and touches every state change |
| a new process (`board`) | isolates the board's failure domain and latency from the orchestrator loop (R-02) | inside the orchestrator: board latency delays runs and timers |
| `OrchestratorService` gains an optional `source` argument | FR-024 and exactly-once recovery (R-07) need the platform's own record to name the board update | a separate mapping table cannot be written in the service's transaction |
