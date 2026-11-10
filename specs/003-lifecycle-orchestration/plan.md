# Implementation Plan: Lifecycle Orchestration

**Branch**: `003-lifecycle-orchestration` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-lifecycle-orchestration/spec.md`

## Summary

`src/adlc/orchestration/` runs every terminal through the same nine-state machine, driven
only by the use case's pinned specs, which it reads through `SpecRegistry` (feature 002).

- **Run state** lives in one row per run (`run.terminal_run`). There is no separate workflow
  engine; this is an ADR-01 change, see [research.md](research.md) R-01.
- **Transitions** come from a pure transition table, so they can be tested first.
- **Signals** are applied one per database transaction. Each applies the state change, its
  activity row and any timers. A closing signal also writes the sign-offs, the ledger record
  and the outcome event in that same transaction (constitution V).
- **Delivery** is by an outbox poller with retries and a dead letter after 5 attempts. The
  router opens a run or signals an existing one; a timer loop fires escalation and
  clarification timers.
- **Agents, reviewer and policy engine** are reached through interfaces, with scriptable stubs
  here; features 004 and 006 replace them.
- **Human actions** are service operations that feature 007 will expose over HTTP.
- **The process**: an `adlc-orchestrator` process runs the poller, the advancer and the timer
  loop, with a heartbeat health check.

## Technical Context

**Language/Version**: Python 3.12 (existing `adlc` package, uv)

**Primary Dependencies**:

- Already used: SQLAlchemy 2, psycopg 3, Alembic, OpenTelemetry, Typer
- New: hypothesis (dev only)

**Storage**: PostgreSQL. Schemas `run` (use cases, runs, transitions, activity, sign-offs,
waivers, clarifications, timers), `events` (outbox, processed events, dead-letter actions,
heartbeat) and `ledger` (baseline table extended with run reference and content). Migration
`0003`.

**Testing**: pytest. Hypothesis property tests on the transition table; testcontainers
integration tests (atomic close, idempotency, dead letter, restart); scenario tests for D-2,
D-3, D-4, D-7, D-9 and a full T0→T9 path, using the real registered `adlc-specs/` and stub
agents.

**Target Platform**: Compose service `orchestrator` (same image as the API), plus developer
machines and CI.

**Project Type**: background service and library inside the platform package.

**Performance Goals**: from a closing commit to the next run open in ≤ 2 s at p95 (SC-003,
NFR-04), using LISTEN/NOTIFY wake-up with a 1 s polling fallback.

**Constraints**:

- No terminal-specific code (constitution I); the no-hard-coded-values scan covers
  `orchestration/`.
- Every state change happens in exactly one transaction; external calls (agent, reviewer,
  policy) happen outside transactions and are applied with an optimistic version check.
- A single orchestrator process in the MVP; leases make a second process safe but are not
  required.

**Scale/Scope**: about 3 concurrent use cases (SA §16), 10 terminals, tens of runs per use case.

### New dependencies and licences (constitution VIII)

| Dependency | Use | Licence |
| --- | --- | --- |
| hypothesis (dev) | Property tests of the transition table | MPL-2.0 |

UUID v7 event ids use a 20-line RFC 9562 implementation in `orchestration/ids.py` (Python 3.12
has no `uuid7`), so no extra package is needed. LangGraph is **not** added in this feature.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Article | How this plan complies | Status |
| --- | --- | --- |
| I Spec-driven | States, signals and routing are generic. Destinations, timers, sign-off roles and subscriptions come from the pinned specs through `SpecRegistry`; the scan is extended to `orchestration/` | Pass |
| II Superset, not values | No use-case values in code; risk tier comes from T0's emitted value | Pass |
| III Agents build, humans decide | The transition table only accepts outcome signals from human actors, and `escalate` only from the orchestrator; property tests prove no other path exists | Pass |
| IV Separation of duties | Policy `authorize` is called for agent tool calls (stub here, enforced in 004/006); human decisions are checked against sign-off roles | Pass |
| V Evidence-first | Close writes run, sign-offs, activity, ledger record (chained hash) and outbox event in one transaction; the next run reads trigger evidence from the ledger and the run record | Pass |
| VI Deterministic first | Prerequisites, controls and conditions go to the policy interface | Pass |
| VII Interfaces | `TerminalRun`, `Router`, `PolicyEngine`, `AgentRunner`, `Reviewer` and `Clock` protocols; stubs implement the same protocols | Pass |
| VIII Open source | hypothesis (MPL-2.0); no other new dependency | Pass |
| IX Test first | Transition table, routing resolution, rework counters and atomic close are written test-first | Pass |
| X Observable | Every step writes `run.run_activity`; spans with `run_id` around policy, agent and reviewer calls and routing | Pass |
| XI Secure | Decisions checked against roles; agents and the reviewer cannot set outcomes; app role grants are minimal (no UPDATE or DELETE on ledger or closed-run history) | Pass |
| XII Simplicity | One state store, one process, a polling loop; reminders deferred (build plan simplify-if-late) | Pass |
| XIII Naming | Tables and columns per Annex A.6; ids per A.5; events per A.3 | Pass |

**Recorded deviation from an earlier proposal (not a constitution violation)**: ADR-01
proposed a LangGraph checkpointer for terminal runs. The user decided on 2026-11-10 to use a
plain PostgreSQL state machine; see research R-01. The `TerminalRun` interface keeps the swap
boundary that SA §17 asks for.

**Post-design re-check**: Pass.

## Project Structure

### Documentation (this feature)

```text
specs/003-lifecycle-orchestration/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/
│   ├── state-machine.md          # states, signals, transition table, effects
│   ├── service-operations.md     # operations 007 will expose; errors
│   ├── interfaces.md             # TerminalRun, Router, PolicyEngine, AgentRunner, Reviewer, Clock
│   └── events.md                 # event envelope, outbox, delivery and dead-letter rules
├── checklists/
└── tasks.md
```

### Source Code (repository root)

```text
src/adlc/orchestration/
├── __init__.py  README.md
├── ids.py            # UC-nnnn, run ids, clarification ids, WVR-nnnn, uuid7
├── durations.py      # TDS B.1 durations → timedelta (h, d, w, m=30d) with ADLC_TIME_SCALE
├── states.py         # RunState, Signal, transition table (pure)
├── interfaces.py     # protocols
├── stubs.py          # StubPolicy, StubAgent, StubReviewer (scriptable)
├── store.py          # SQL access for run/events/ledger tables (one transaction per call)
├── engine.py         # PostgresTerminalRun: apply(signal) and advance(run) (automatic steps)
├── routing.py        # resolve destinations, templates, event routes (pure, over SpecRegistry)
├── router.py         # Router: event → open or signal runs, rework counters, pins
├── outbox.py         # poller, retries, dead letters, re-queue, LISTEN/NOTIFY
├── timers.py         # timer loop (escalate_after, clarification_sla)
├── ledger.py         # baseline ledger record content + chained hash (005 extends)
├── service.py        # OrchestratorService: human and admin operations
├── worker.py         # run loop: poll outbox, advance runs, fire timers; heartbeat
└── __main__.py       # `adlc-orchestrator` (run | health)
scripts/demo_drive.py # drives the service through a scenario on the live stack (quickstart §4)
db/migrations/versions/0003_orchestration.py
deploy/compose.yaml   # + orchestrator service (after register)
tests/
├── unit/orchestration/          # states (hypothesis), routing, durations, ids, ledger hashing
├── integration/orchestration/   # atomic close, idempotency, dead letter, restart, ordering
└── scenario/                    # D-2, D-3, D-4, D-7, D-9, T0→T9 with stubs
```

**Structure Decision**: the layer module `orchestration/` from build plan §5 is filled here.
Pure decision logic (`states.py`, `routing.py`, `durations.py`, `ids.py`) is separate from I/O
(`store.py`, `engine.py`, `outbox.py`, `timers.py`), so the core rules are tested without a
database.

## Complexity Tracking

No constitution violations; nothing to justify.
