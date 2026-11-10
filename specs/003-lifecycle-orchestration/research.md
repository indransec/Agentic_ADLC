# Research: Lifecycle Orchestration (003)

## R-01 Run engine: plain PostgreSQL state machine (ADR-01 change)

- **Decision** (user, 2026-11-10): each terminal run is one row in `run.terminal_run`, and its
  state changes only through `TerminalRun.apply(run_id, signal)`. Each call is one transaction
  that locks the run row (`SELECT … FOR UPDATE`), checks the transition table, and writes the
  new state with its effects. LangGraph is not used for terminal runs; it remains the choice
  for agent graphs in feature 006.
- **Rationale**:
  - Human waits last days and are resumed by outside signals, so a run is mostly at rest.
  - One store means no second copy of run progress to keep in step with the run table the
    inbox and dashboard read.
  - Closing writes the run, ledger record and outbox event in one transaction, which makes
    constitution V trivially atomic.
  - Restart safety is the database itself.
  - The transition table is a pure function, which can be exhaustively and property-tested.
- **Alternatives**: LangGraph StateGraph with the Postgres checkpointer (build plan §8,
  proposed ADR-01). It adds a second state store, an idempotent-close requirement across two
  stores, and three dependencies. Temporal (SA §17 alternative) is too heavy for the MVP.
- **Follow-up**: record ADR-01 as "PostgreSQL state machine behind `TerminalRun`; LangGraph
  for agents" and update SA §17 and build plan §4 and §8.

## R-02 Automatic steps outside transactions

- **Decision**: states that need work without a human (`opened`, `building`, `checking`,
  `reviewing`) are *automatic*. The advancer:
  1. leases a run (`lease_until`) with `FOR UPDATE SKIP LOCKED`;
  2. calls the policy, agent or reviewer **outside** any transaction;
  3. applies the result as a signal carrying the run's `version`.

  If the version moved meanwhile (a human terminated the run, a timer fired), the result is
  discarded and recorded as stale (FR-030b). Leases expire, so after a crash the step is
  retried; each retry counts toward `max_auto_retries`, and beyond it the run escalates with
  trigger `retry_limit` (FR-030a).
- **Rationale**: real agent calls take minutes (006); holding a transaction or row lock for
  that long is wrong. The optimistic version check keeps concurrent signals safe.

## R-03 Signals and the transition table

- **Decision**: a signal has a `kind`, an `actor` (type and id) and a payload. The pure
  function `transition(state, signal, ctx) -> Outcome(next_state, effects)` rejects anything
  not in the table ([contracts/state-machine.md](contracts/state-machine.md)). Effects are
  data, for example `CloseRun(status)`, `StartTimer(kind, after)`, `CancelTimers`,
  `IncrementAutoRetry`, `RecordClarification`, `ProposeWaiver`. The engine executes them in
  the same transaction.
- **Outcome rights** are part of the table (constitution III):
  - `decide` signals are accepted only from actor type `human`;
  - `escalate` only from `orchestrator`;
  - `agent_result` and `review_result` only from `agent` and `reviewer`.

  A hypothesis test generates arbitrary signal sequences and asserts that no run ever closes
  with pass, rework, exception or terminate without a human decision, and that no run reaches
  `escalated` without an orchestrator signal.

## R-04 Waiver (two-step exception)

- **Decision**: no tenth state. While `awaiting_sign_off`, an `exception` decision with the
  required fields creates `run.waiver` with status `proposed`, and the run records
  `pending_waiver_id`.
  - The next accepted signal is `waiver_decision` from a person holding the approver role (the
    exception's `set_by`, else the terminal's A), who is not the proposer.
  - Approve closes the run with `exception`.
  - Reject sets the waiver to `rejected`, clears the pending waiver and leaves the run in
    `awaiting_sign_off` for a new decision.
- **Rationale**: keeps SA §6.2's nine states unchanged (spec clarification 1).

## R-05 Router and rework counters

- **Decision**: `Router.handle(event)` runs in the delivery transaction, together with the
  `processed_event` insert (idempotency). For each terminal whose **pinned** version subscribes
  to the event type:
  - **If an active run exists** for (use case, terminal): apply the signal `event_received`.
    Blocked runs re-check prerequisites; other states record the event in the run's context.
  - **Otherwise**: open run `k + 1`, with `rework_count` = number of earlier runs of that
    terminal for that use case opened by a `*.rework.*` event, plus one if this event is a
    rework. If `rework_count > max_rework_cycles`, the run opens directly in `escalated`
    (trigger `rework_limit`).
  - **Run mode**: `retire` when the trigger is a `<terminal>.terminate` event, else `evolve`;
    exposed to expressions as `run.mode`.
  - **Trigger evidence** (rework comment, root cause, causing run id, ledger key) is copied
    from the event payload into the new run's context.
- **Use case without pins** (`usecase.submitted`): pins are written at submit, before the event.

## R-06 Routing destinations (pure, `routing.py`)

- **Decision**: on close, the engine:
  1. looks up the outcome route through `SpecRegistry` (pinned version);
  2. writes **one outcome event**, `T<n>.<status>[.<root_cause>]`;
  3. handles the destination by kind.

  The router then opens subscribers. Destination kinds:

  | Kind | Handling |
  | --- | --- |
  | `terminal` | Nothing extra; the subscription opens it (002 rule V-17 guarantees it) |
  | `template` | Resolve `${T<n>.<artifact>.<column>}` from the closing run's artifacts (first row); must name a change-class re-entry terminal or the decision is refused; emit `T<n>.reentry.T<k>` |
  | `special/terminating` (`lifecycle_closed`) | Close the use case lifecycle |
  | `special/continue` | Schedule the next review run of the same terminal (continuous mode) |
  | `special/human` | Applies to escalate: the run stays `escalated` with the destination recorded |
  | `special/terminal_resolver` (`owning_terminal`) | Take the terminal named in the decision; emit `T<n>.rework.<cause>` with `target_terminal` in the payload; the router opens that terminal even without a subscription (the only routed open not driven by a subscription) |
  | `special/external` (`itsm`) | Recorded as handed off |
  | `disabled` | The decision is refused |

  **Terminate cascade** (FR-018c): a terminate close also closes every other active run of the
  use case with `terminate` (reason "lifecycle terminated"), cancels their timers and sets the
  use case to `terminated`, all in the same transaction.

  T8 operational events (`raise_operational_event`) go out as `T8.event.<name>`; the router
  records the event route's `immediate` actions on the T8 run and evaluates `then_when` through
  the policy interface to emit the follow-on event (for example `T7.rollback`).

## R-07 Timers and the time scale

- **Decision**: `run.timer` rows with run, kind (`escalate_after`, `clarification_sla`,
  `review_due`), `due_at`, `fired_at` and `cancelled_at`.
  - `escalate_after` starts at open; `clarification_sla` when a clarification is raised;
    `review_due` for continuous terminals.
  - The timer loop takes due, unfired, uncancelled timers (`FOR UPDATE SKIP LOCKED`), applies
    signal `timer(kind)` and sets `fired_at`, so an overdue timer fires once after downtime.
  - State changes that make a timer moot cancel it.
- **Durations**: TDS B.1 strings (`7d`, `72h`, `12m` = 360 days). The setting
  `ADLC_TIME_SCALE` (default `1.0`) multiplies every timer, so `0.0001` makes a 7-day timer
  last about one minute in the demo.
- **Risk tier**: the use case tier once T0 has passed (emitted `risk_tier`, supplied in the pass
  decision, FR-018a), else `medium`.
- **Continuous terminals** (FR-018b): a `continue` close starts a `review_due` timer from
  `review_schedule` (weekly 7d, fortnightly 14d, monthly 30d). When it fires, the timer loop
  opens the next review run of the terminal, triggered by the previous run's pass event.
- **`escalate_after`** is measured from run open; an `escalated` run ignores the timer.

## R-08 Outbox, delivery, ordering, dead letters

- **Decision**: `events.outbox_event` rows are written in the closing transaction. The writing
  transaction sends `NOTIFY adlc_outbox`; the worker `LISTEN`s, falling back to a 1 s poll.
  - **Ordering per use case**: the poller takes the oldest due event whose use case has no
    older event that is still pending and not dead-lettered (`FOR UPDATE SKIP LOCKED`).
  - **Success**: `Router.handle` plus the `processed_event` insert commit together.
  - **Failure**: a separate transaction increments `attempts`, stores `last_error` and sets
    `next_attempt_at` by the schedule 10 s, 1 min, 5 min, 15 min.
  - **Dead letter**: after the fifth failure, `dead_lettered_at` is set (and later events of
    that use case are unblocked).
  - **Re-queue**: resets `attempts`, `next_attempt_at` and `dead_lettered_at`, and writes
    `events.dead_letter_action` (who, when).
- **Fault injection for tests**: `Router` accepts an optional hook that raises for chosen event
  ids, so dead-lettering is tested without monkeypatching internals.

## R-09 Ledger record (baseline, extended in 005)

- **Decision**: migration `0003` adds `run_id`, `usecase_id` and `content_json` (jsonb) to
  `ledger.ledger_record`; the append-only triggers stay.
  - **Content**: run id, terminal, spec version and spec hash, trigger event, final status,
    decisions with deciders, reviewer recommendation, artifacts (inline for now), control
    results, clarification rounds, waiver.
  - **Hashes**: `content_hash` is `sha256` of the normalised content (002 `normalise`);
    `previous_record_hash` is the latest record of the same use case, read under a lock on the
    `run.usecase` row so the chain cannot fork.
- **005** adds the artifact store, record verification and the full schema.

## R-10 Stubs

- **Decision**:
  - **`StubAgent`** builds, for every applicable artifact in the pinned spec, one row with
    each column set to `"<column> (stub)"`. A per-test script can override values (for
    example T9 `change_impact_assessment.reentry_terminal = "T2"`), raise a clarification, or
    report `budget_exceeded`.
  - **`StubReviewer`** recommends `pass` and scores every checklist item 1, unless scripted.
  - **`StubPolicy`** returns `True` for prerequisites, controls, conditions and `authorize`,
    unless scripted per (terminal, id).
  - Scripts are plain dictionaries keyed by terminal and call number.

## R-11 Orchestrator process and health

- **Decision**: `adlc-orchestrator run` loops: drain the outbox, then advance leased automatic
  runs, then fire due timers, then wait (notify or 1 s). Each loop writes
  `events.orchestrator_heartbeat`. `adlc-orchestrator health` exits 0 if the heartbeat is under
  30 s old; Compose uses it as the healthcheck (001 FR-003).
- Settings: `OrchestratorSettings(DatabaseSettings)` adds the app password, OTLP endpoint,
  `ADLC_TIME_SCALE`, `ADLC_POLL_INTERVAL` (default `1s`) and `ADLC_LEASE` (default `5min`).
- **Tests** use `Worker.drain()`, which repeats outbox, advance and timers until nothing is
  left, so scenarios are deterministic.

## R-12 Authorisation of human operations

- **Decision**: service operations take an `Actor`: the `Person` from 001 identity (account
  and roles) or the system. Rules:
  - **Decide**: the person holds a role in the applicable sign-off rule (FR-009b). A `plus`
    approver whose condition holds (policy interface) is required in addition to
    `min_approvers`. Board and external approvals are recorded only (FR-009c). The rule is the plain
    rule, `by_tier[risk tier]`, or `by_mode[run.mode]`; `plus` roles count when their condition
    holds (policy interface).
  - **Terminate**: additionally restricted to the outcome's `set_by` when given.
  - **Waiver**: the approver role (R-04).
  - **Clarification answers**: the addressed role.
  - **Escalation completion**: the terminal's A role.
  - **Dead-letter re-queue**: role `adlc_coe`, read from configuration
    (`ADLC_DEADLETTER_ROLE`, default `adlc_coe`) so no role name is hard-coded.
