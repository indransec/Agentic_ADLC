# adlc.orchestration

Lifecycle orchestration (feature 003). Every terminal T0–T9 runs the same state machine, driven
only by the use case's **pinned** specs, which are read through `SpecRegistry` (feature 002).
There is no terminal-specific code here: a scan in `tests/unit/test_no_hardcoded_values.py`
checks for terminal ids, event names, role ids and route destination names.

## How a run moves

```text
opened ─► building ─► checking ─► reviewing ─► awaiting_sign_off ─► closed
  │           │  ▲         │                         │  ▲
  ▼           ▼  └─retry───┘                         │  └─ waiver rejected
blocked   awaiting_clarification                      ▼
                                        escalated ─► awaiting_sign_off (completed by A role)
```

- **States, signals and allowed actors** are defined in `states.py`, a pure transition table
  (contract: `specs/003-lifecycle-orchestration/contracts/state-machine.md`). Hypothesis
  property tests prove:
  - only human decisions close a run with an outcome;
  - only the orchestrator's rules escalate.
- **The engine** (`engine.py`, `PostgresTerminalRun`) applies one signal per transaction:
  1. lock the run row;
  2. run `transition()`;
  3. execute the effects;
  4. write `run.run_transition` and `run.run_activity`.

  A closing signal writes the sign-offs, the chained ledger record and the outcome event in
  the same transaction (constitution V).
- **Automatic steps** (prerequisites, build, controls, review) are run by `advance()`:
  1. lease the run;
  2. call the policy engine, agent or reviewer **outside** any transaction;
  3. apply the result with a version check.

  A result for a run that moved on is recorded as `stale`. An expired lease counts as an
  automatic retry.

## Modules

| Module | Role |
| --- | --- |
| `states.py` | Pure transition table, effects, outcome rights |
| `spec_view.py`, `routing.py` | Pure reads and routing decisions over a pinned spec |
| `ids.py`, `durations.py`, `ledger.py` | Identifiers and UUID v7; TDS durations and the time scale; ledger content and hash |
| `store.py` | All SQL; every function takes the caller's connection |
| `engine.py` | `PostgresTerminalRun`: `open_in`, `apply`, `apply_in` and `advance` |
| `router.py` | Event → open or signal runs; self-routes and resolver destinations; event routes |
| `outbox.py` | Ordered delivery per use case, idempotency, retries (10 s, 1 min, 5 min, 15 min), dead letter after 5 |
| `timers.py` | `escalate_after`, `clarification_sla` and `review_due` (continuous terminals) |
| `service.py` | `OrchestratorService`, the human and admin operations (exposed by feature 007) |
| `interfaces.py`, `stubs.py` | `PolicyEngine`, `AgentRunner`, `Reviewer`, `Clock` and their scriptable stubs |
| `worker.py`, `__main__.py` | The `adlc-orchestrator run` loop (LISTEN `adlc_outbox`, 1 s fallback) and `health` |

## Replacing the stubs

- **Feature 004** implements `PolicyEngine.evaluate` and `authorize`. It receives the check id
  (`PRE-…`, `CTL-…`, `plus:<role>`, `then_when:<event>`) in `EvalContext`.
- **Feature 006** implements `AgentRunner.build` and `Reviewer.review`. The reviewer never sees
  the builder's reasoning.

To switch, wire the real implementations in `__main__.py` (`build_orchestrator`).

## Settings

| Setting | Meaning |
| --- | --- |
| `ADLC_TIME_SCALE` | Multiplies every timer and retry delay (demo: `0.0001`) |
| `ADLC_POLL_INTERVAL` | Polling fallback when no notification arrives |
| `ADLC_LEASE` | How long an automatic step may run before it counts as interrupted |
| `ADLC_HEARTBEAT_MAX_AGE` | Health threshold |
| `ADLC_DEADLETTER_ROLE` | Role allowed to list and re-queue dead letters; required, so no role name is in code |
