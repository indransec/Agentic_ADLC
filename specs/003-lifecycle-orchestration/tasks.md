# Tasks: Lifecycle Orchestration

**Input**: Design documents from `specs/003-lifecycle-orchestration/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: required. Constitution IX makes the core test-first: the transition table, routing
resolution, rework counters and atomic close. In every story, test tasks come first and must
fail before the implementation task that follows them.

**Organization**: phases follow the spec's user stories in priority order (US1–US4 P1, US5–US6
P2). Basic outbox delivery is part of US1 because the lifecycle cannot move without it.
Retries, dead letters and restart safety are in US6.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to (US1–US6)

## Conventions used by every task

- Code lives in `src/adlc/orchestration/`, unit tests in `tests/unit/orchestration/`,
  database tests in `tests/integration/orchestration/` (testcontainers, `tests/support/pg.py`),
  and scenario tests in `tests/scenario/`.
- Scenario and integration tests register the **real** `adlc-specs/` with the 002 registration
  code before running.
- No terminal ids, event names or role names in `src/` (constitution I). Tests may name them.
- Every state change goes through `TerminalRun.apply` in one transaction (research R-01).

---

## Phase 1: Setup

- [ ] T001 Add `hypothesis` as a dev dependency in `pyproject.toml`, refresh `uv.lock`, and record it (MPL-2.0) in the licence table of `specs/003-lifecycle-orchestration/plan.md` if it is not already there
- [ ] T002 [P] Write failing tests for `OrchestratorSettings` in `tests/unit/test_settings.py`: `ADLC_TIME_SCALE` (float > 0, default `1.0`), `ADLC_POLL_INTERVAL` (default `1s`), `ADLC_LEASE` (default `5min`), `ADLC_DEADLETTER_ROLE` (default `adlc_coe`, must exist in `adlc-specs/shared/roles.yaml`), `ADLC_HEARTBEAT_MAX_AGE` (default `30s`); invalid values fail at start with the setting name
- [ ] T003 Implement `OrchestratorSettings(DatabaseSettings)` in `src/adlc/config/settings.py` (app password and OTLP endpoint as in `Settings`, plus the T002 fields using the 001 `Duration` type) and add the new variables with comments to `.env.example`
- [ ] T004 [P] Write failing migration tests in `tests/integration/orchestration/test_migration_0003.py`: every table and column in data-model.md exists; `run.usecase.usecase_id` matches `^UC-[0-9]{4}$`; `run.waiver.waiver_id` matches `^WVR-[0-9]{4}$`; the partial unique index "one active run per (usecase_id, terminal_id) WHERE state <> 'closed'"; append-only triggers on `run.run_transition`, `run.run_activity`, `run.sign_off`, `run.clarification_round`, `run.clarification_answer` and `events.dead_letter_action` (SQLSTATE 42501 for every identity); closed `run.terminal_run` rows cannot be updated; `events.outbox_event` allows updates only to `attempts`, `next_attempt_at`, `processed_at`, `dead_lettered_at`, `last_error`; `run.waiver` allows updates only to `status`, `decided_by`, `decided_at` while `status = 'proposed'`; `run.usecase` allows updates only to `risk_tier`, `status`, `closed_at`; `ledger.ledger_record` gains `run_id`, `usecase_id`, `content_json` with a unique index on `run_id` and stays append-only; app-role grants exactly as in data-model.md (including INSERT on `spec.usecase_spec_pin`); downgrade to 0002 and upgrade again work
- [ ] T005 Write migration `db/migrations/versions/0003_orchestration.py` (schemas `run` and `events`, tables, sequences `run.usecase_seq` and `run.waiver_seq`, indexes, triggers, grants, `ledger.ledger_record` columns) so T004 passes; update 001's ledger privilege test in `tests/integration/test_ledger_immutability.py` only if the new grants change what it asserts
- [ ] T006 [P] Create the package `src/adlc/orchestration/__init__.py` and a stub `src/adlc/orchestration/README.md` (module map from plan.md only; T073 writes the full README), add `*/adlc/orchestration/*` to `CORE_MODULES` in `Makefile`, register the `adlc-orchestrator = "adlc.orchestration.__main__:main"` script in `pyproject.toml`
- [ ] T007 [P] Add shared test fixtures: `tests/integration/orchestration/conftest.py` (migrated database, real `adlc-specs/` registered, `adlc_app` engine, a `FakeClock`, scripted stubs, an `OrchestratorService` and `Worker` wired together) and `tests/scenario/conftest.py` reusing them; replace the placeholder text in `tests/scenario/README.md` with what 003 adds there

**Checkpoint**: settings load, migration 0003 applies and reverts, fixtures build.

---

## Phase 2: Foundational (blocks every story)

### Tests first

- [ ] T008 [P] Write failing tests in `tests/unit/orchestration/test_ids.py`: use case ids `UC-0001` from a sequence number, run ids `<usecase_id>/T<n>/run-<k>` built and parsed, clarification ids `<run_id>/clar-<k>`, waiver ids `WVR-0001`; `uuid7()` returns version-7 UUIDs that sort by creation time within one millisecond burst (RFC 9562)
- [ ] T009 [P] Write failing tests in `tests/unit/orchestration/test_durations.py`: TDS B.1 strings `72h`, `7d`, `2w`, `12m` (m = 30 days) parse; anything else raises with the offending value; `scaled(duration, time_scale)` multiplies; review schedules `weekly`, `fortnightly`, `monthly` map to 7d, 14d, 30d
- [ ] T010 [P] Write failing exhaustive tests in `tests/unit/orchestration/test_states.py`: one test per row of contracts/state-machine.md (state, signal, condition → next state and effects); every (state, signal kind) pair not in the table raises `InvalidTransition`; each signal kind is refused from any actor type other than the one listed in "Signals and allowed actors"; `closed` accepts nothing; `timer escalate_after` is ignored in `escalated` (FR-021)
- [ ] T011 [P] Write failing hypothesis property tests in `tests/unit/orchestration/test_state_properties.py` over random signal sequences with random actor types: (1) no sequence without a `human` signal reaches `closed` with pass, rework, exception or terminate; (2) `escalated` is only entered by an `orchestrator` signal; (3) `closed` accepts no signal; (4) `clarification_answered` and `escalation_completed` never change `rework_count`
- [ ] T012 [P] Write failing tests in `tests/unit/orchestration/test_ledger_content.py`: `build_record_content(...)` contains run id, terminal, spec version, spec hash, trigger event, final status, decisions with deciders, reviewer recommendation, artifacts, control results, clarification rounds and waiver; `content_hash` is SHA-256 of the 002 `normalise` output and is stable under key reordering; `previous_record_hash` chains to the given previous hash (None for the first record of a use case)

### Implementation

- [ ] T013 [P] Implement `src/adlc/orchestration/ids.py` (T008)
- [ ] T014 [P] Implement `src/adlc/orchestration/durations.py` (T009). Do not reuse `adlc.config.durations`: it rejects `m`, which TDS B.1 uses for months
- [ ] T015 Implement `src/adlc/orchestration/states.py`: `RunState`, `SignalKind`, `ActorType`, `Signal`, `TransitionContext` (spec limits, counters, pending waiver, sign-offs so far, required approvals), effect dataclasses (`CloseRun`, `StartTimer`, `CancelTimer`, `CancelAllTimers`, `RecordSignOff`, `ProposeWaiver`, `DecideWaiver`, `RecordClarification`, `IncrementAutoRetry`, `StoreArtifacts`, `StoreControls`, `StoreRecommendation`, `SetReturnState`, `Escalate(trigger)`, `RecordEvent`), and the pure `transition()` (T010, T011)
- [ ] T016 [P] Implement `src/adlc/orchestration/interfaces.py` per contracts/interfaces.md: `TerminalRun`, `Router`, `PolicyEngine` (`evaluate`, `authorize`), `AgentRunner` (`build` → `Artifacts` | `Clarification` | `BudgetExceeded`), `Reviewer` (`review` → `Recommendation` | `Clarification`), `Clock`; `BuildContext` and `ReviewContext` with the fields in contracts/interfaces.md (`ReviewContext` must not carry builder reasoning)
- [ ] T017 [P] Write tests and implement `src/adlc/orchestration/stubs.py` with `tests/unit/orchestration/test_stubs.py`: `StubAgent` builds one row per applicable artifact with each column `"<column> (stub)"`, script overrides by (terminal, call number) for values, clarifications and `budget_exceeded`; `StubReviewer` recommends pass with every checklist item scored 1 unless scripted; `StubPolicy` returns true for prerequisites, controls, conditions and `authorize` unless scripted per (terminal, id) (research R-10)
- [ ] T018 Implement `src/adlc/orchestration/ledger.py` (T012)
- [ ] T019 Implement `src/adlc/orchestration/store.py`: SQL for every table in data-model.md (load run `FOR UPDATE`, insert run, update run with `version` check, insert transition, activity, sign-off, waiver, clarification, answer, timer; outbox insert with `NOTIFY adlc_outbox`; ledger insert reading the previous hash under a `FOR UPDATE` lock on the `run.usecase` row; pins read and write); every function takes a connection so callers own the transaction; full literal SQL only (no f-string SQL, ruff S608)
- [ ] T020 [P] Add a tracing helper `span(component, operation, run)` in `src/adlc/orchestration/tracing.py` producing spans `adlc.<component>.<operation>` with `run_id`, `usecase_id`, `terminal_id` attributes using the 001 tracer, with a unit test in `tests/unit/orchestration/test_tracing.py`
- [ ] T021 Write failing tests in `tests/integration/orchestration/test_engine_apply.py`: `PostgresTerminalRun.apply` locks the run, applies `transition()`, writes `run.run_transition` and `run.run_activity`, executes effects and increments `version` in one transaction; a stale `expected_version` raises `StaleRun` and writes nothing; an `InvalidTransition` writes nothing; on `CloseRun` the run, sign-offs, activity, ledger record and outbox event commit together, and an injected failure after the ledger insert leaves none of them (SC-007, atomic close); closing cancels every open timer and frees the active-run slot; two runs of the same use case closed concurrently produce one unbroken chain (the second record's `previous_record_hash` is the first record's `content_hash`, never the same predecessor twice)
- [ ] T022 Implement `apply()` and `open()` in `src/adlc/orchestration/engine.py` so T021 passes; `open()` resolves the pinned spec through `SpecRegistry`, the tier from the use case (else `medium`), sets `due_at` from `expected_duration`, and starts the `escalate_after` timer (FR-021)

**Checkpoint**: the state machine is proven in isolation and runs are changed only through one-transaction `apply`.

---

## Phase 3: User Story 1 – Submitted use case flows terminal to terminal (P1) 🎯 MVP

**Goal**: submit → T0 opens → each run goes prerequisites → build → controls → review → sign-off → close → next terminal opens.

**Independent test**: with stubs that always succeed and scripted pass decisions, a full T0→T9 lifecycle completes (SC-001).

### Tests first

- [ ] T023 [P] [US1] Write failing unit tests in `tests/unit/orchestration/test_routing.py` for pure routing resolution over an `InMemorySpecRegistry` of the real specs: subscribers of an event type for a set of pins; outcome route for pass, rework by root cause, exception, terminate; destination kinds `terminal`, `template`, `special` (`terminating`, `continue`, `human`, `terminal_resolver`, `external`) and `disabled` handled as in research R-06; emitted values that are not artifacts are required in the pass decision (FR-018a); sign-off rule selection: plain, `by_tier[<tier>]`, `by_mode[<mode>]`, with `plus` approvers required in addition to `min_approvers` when their condition holds (FR-009b)
- [ ] T024 [P] [US1] Write failing integration tests in `tests/integration/orchestration/test_submit_and_open.py`: `submit_usecase` creates `UC-nnnn` with the submitter as business owner, pins the active version of every registered terminal, writes `usecase.submitted`; delivering it opens exactly one T0 run `UC-nnnn/T0/run-1` with `mode=evolve`; `NoActiveSpecs` when nothing is registered; after a newer version of a terminal is registered mid-lifecycle, the use case's next run of that terminal still opens on the pinned version (spec Edge Cases)
- [ ] T025 [P] [US1] Write failing integration tests in `tests/integration/orchestration/test_advance.py`: the advancer leases an automatic run (`lease_until`, `FOR UPDATE SKIP LOCKED`), calls policy, agent and reviewer outside any transaction, and applies the result with the run's `version`; prerequisites met → building; `on_missing: block` unmet → blocked (US1/AC4); a blocked run re-checks when a subscribed event arrives (`event_received` → opened); a failing blocking control returns the run to building and increments `auto_retries` but not `rework_count` (US1/AC5); every step writes `run.run_activity` with step, actor and outcome (constitution X)
- [ ] T026 [P] [US1] Write failing integration tests in `tests/integration/orchestration/test_sign_off_pass.py`: a pass by a non-holder raises `NotAuthorised`; with `min_approvers: 2` one pass keeps the run awaiting sign-off and the second distinct approver closes it (US2/AC3); the same person passing twice counts once; a required `plus` approver whose condition holds is still needed after `min_approvers`; a pass missing an emitted value (T0 `risk_tier`) raises `InvalidDecision`; closing T0 sets `run.usecase.risk_tier`; the pass writes `T<n>.pass` whose payload holds `ledger_key`, `status` and `emits`
- [ ] T027 [P] [US1] Write failing integration tests in `tests/integration/orchestration/test_delivery_basic.py`: the outbox processor delivers events to `Router.handle` in `created_at` order per use case; `Router.handle` and the insert into `events.processed_event` commit together; a subscribing terminal opens; a terminal without a subscription does not (FR-015)

### Implementation

- [ ] T028 [US1] Implement `src/adlc/orchestration/routing.py` (pure: subscribers, outcome destination resolution, template resolution, sign-off rule selection, required decision fields) so T023 passes
- [ ] T029 [US1] Implement `advance()` in `src/adlc/orchestration/engine.py` (lease, call stub interfaces inside `tracing.span`, apply with `expected_version`, release lease) so T025 passes
- [ ] T030 [US1] Implement `src/adlc/orchestration/router.py` `PostgresRouter.handle` for subscription opens and `event_received` to active runs (rework counting and resolver opens come in US2) so T024 and T027 pass
- [ ] T031 [US1] Implement the delivery loop in `src/adlc/orchestration/outbox.py` (`process_next(conn)`: pick the oldest due event of a use case with no older pending event, `FOR UPDATE SKIP LOCKED`, call the router, mark processed); retries and dead letters come in US6
- [ ] T032 [US1] Implement `OrchestratorService` in `src/adlc/orchestration/service.py` with `Actor`, typed errors (`NotAuthorised`, `InvalidDecision`, `StaleRun`, `InvalidTransition`, `NoActiveSpecs`), `submit_usecase`, `decide` for pass (sign-off rule from `routing.py`, emitted values, `reason` when differing from the recommendation), `get_run`, `list_runs`, `get_usecase` so T024 and T026 pass
- [ ] T033 [US1] Implement `Worker.drain()` in `src/adlc/orchestration/worker.py`: repeat deliver outbox → advance automatic runs → fire due timers until nothing changes (no sleeping; the long-running loop comes in Phase 9)
- [ ] T034 [US1] Write and pass the happy-path scenario in `tests/scenario/test_happy_path.py`: submit, then for each opened run pass with the required approvers (separate accounts per role) until the lifecycle reaches T9; assert one closed run per terminal T0–T8, a T9 run, one ledger record per closed run with an unbroken hash chain, and an outcome event per close (SC-001, SC-007)

**Checkpoint**: MVP — the lifecycle moves end to end with stubs.

---

## Phase 4: User Story 2 – Human decisions route the lifecycle (P1)

**Goal**: rework by root cause, exceptions with waivers, terminate, and the evidence carried to the next run.

**Independent test**: reject T1 with a comment and root cause `requirement`; T1 run 2 opens with that comment in its build context (D-2).

### Tests first

- [ ] T035 [P] [US2] Write failing unit tests in `tests/unit/orchestration/test_rework_counter.py` for the rework rule (research R-05): `rework_count` = earlier runs of that terminal for that use case opened by a `*.rework.*` event, plus one if this event is a rework; clarifications, control retries and escalation completion add nothing; `count > max_rework_cycles` means open escalated with trigger `rework_limit`
- [ ] T036 [P] [US2] Write failing integration tests in `tests/integration/orchestration/test_decisions.py`: rework without comment or root cause raises `InvalidDecision` (US2/AC1); a root cause with no route raises; a decision differing from the recommendation without `reason` raises (US2/AC4); a non-holder raises `NotAuthorised` (US2/AC5); terminate needs a reason and is limited to the outcome's `set_by`; `not_allowed` outcomes are refused; two `decide` calls with the same `expected_version` at the same time: one wins and the other raises `StaleRun`; every refused decision writes nothing
- [ ] T037 [P] [US2] Write failing integration tests in `tests/integration/orchestration/test_rework_routing.py`: T4 rework with root cause `implementation` writes `T4.rework.implementation` and opens a T3 run (US2/AC2); the new run's `trigger_context` holds comment, root cause, causing run id and ledger key and these reach `BuildContext.trigger`, with the previous artifacts in `previous_artifacts`; the rework count of the target terminal increases by one; T6 rework to `owning_terminal` needs `target_terminal` and opens that terminal without a subscription (FR-015 exception)
- [ ] T038 [P] [US2] Write failing integration tests in `tests/integration/orchestration/test_waiver.py`: an exception without waiver owner, expiry (in the future) or compensating control, or a required field such as `risk_acceptance`, raises `InvalidDecision`; a complete exception creates `WVR-nnnn` `proposed` and keeps the run awaiting sign-off; approval by the proposer raises `NotAuthorised`; approval by the approver role closes the run `exception` and writes `T<n>.exception`; rejection marks the waiver `rejected` and lets a new decision be made (FR-012a, US2/AC7)
- [ ] T039 [P] [US2] Write failing integration tests in `tests/integration/orchestration/test_terminate_cascade.py`: terminating a run closes it `terminate`, writes `T<n>.terminate`, closes every other active run of the use case with reason "lifecycle terminated", cancels all their timers, sets the use case `terminated`, all in one transaction (FR-018c, US2/AC6); later events for the use case are recorded and ignored
- [ ] T040 [P] [US2] Write failing integration tests in `tests/integration/orchestration/test_sign_off_rules.py`: a `by_tier` rule picks approvers by the use case tier; a `by_mode` rule picks `retire` approvers for a run opened by a `<terminal>.terminate` event (FR-009b); board and external approvals are recorded as notifications and do not block the close (FR-009c)

### Implementation

- [ ] T041 [US2] Add rework counting and the escalated-open decision to `src/adlc/orchestration/router.py` (pure helper in `routing.py`) so T035 passes
- [ ] T042 [US2] Extend `OrchestratorService.decide` in `src/adlc/orchestration/service.py` for rework, exception and terminate validation, and `decide_waiver`, so T036 and T038 pass
- [ ] T043 [US2] Extend close handling in `src/adlc/orchestration/engine.py` for rework (`T<n>.rework.<cause>` with `target_terminal`), exception (waiver approved) and terminate with the cascade, so T037, T038 and T039 pass
- [ ] T044 [US2] Extend `src/adlc/orchestration/router.py` for resolver opens, trigger context copying and run mode, so T037 and T040 pass
- [ ] T045 [P] [US2] Write and pass scenarios `tests/scenario/test_d2_rework_with_comment.py` (D-2), `tests/scenario/test_d3_rework_root_cause.py` (D-3: T4 `implementation` → T3) and `tests/scenario/test_d5_exception_waiver.py` (D-5: T5 exception proposed by the owner, approved by `risk_owner`, routes to T6)

**Checkpoint**: every human decision routes as the pinned specs say.

---

## Phase 5: User Story 3 – Escalation after limits and human completion (P1)

**Goal**: the orchestrator alone escalates on rework limit, timer, retry limit or budget; the accountable owner completes the run.

**Independent test**: rework T1 three times; the fourth rework opens T1 run 5 directly in `escalated` (D-4).

### Tests first

- [ ] T046 [P] [US3] Write failing integration tests in `tests/integration/orchestration/test_escalation.py`: the fourth rework with `max_rework_cycles: 3` opens escalated with trigger `rework_limit` (US3/AC1); `escalate_after` measured from open escalates a waiting run, including `blocked`, with trigger `timer`, and an escalated run does not escalate again (US3/AC2, FR-021); control failures beyond `max_auto_retries` escalate with `retry_limit`; agent `budget_exceeded` escalates with `budget` (FR-022); entering `escalated` writes `T<n>.escalate` with the trigger; `complete_escalation` by the terminal's A role stores the artifacts and moves to `awaiting_sign_off` (US3/AC3), by anyone else raises `NotAuthorised`; no service operation lets a person or agent set `escalate` (US3/AC4); an escalate route to a human or board destination (for example `release_board`) records the destination on the run and completion still goes to the terminal's A role (spec Edge Cases)
- [ ] T047 [P] [US3] Write failing integration tests in `tests/integration/orchestration/test_timers.py`: timers are scaled by `ADLC_TIME_SCALE`; a timer that fires for a closed run is ignored, except `review_due`, which survives the close and makes the router open the next review run (FR-018b); a due timer fires exactly once even when found late after downtime (`fired_at` set in the same transaction as the signal); cancelled timers never fire; durations come from the pinned spec's timeline for the use case tier

### Implementation

- [ ] T048 [US3] Implement `src/adlc/orchestration/timers.py` (`fire_due(conn, clock)`: due, unfired, uncancelled timers `FOR UPDATE SKIP LOCKED`, apply `timer(kind)`, set `fired_at`) and wire it into `Worker.drain()` so T047 passes
- [ ] T049 [US3] Add escalation effects to `src/adlc/orchestration/engine.py` (trigger stored, `T<n>.escalate` outbox event, timers cancelled) and `complete_escalation` to `src/adlc/orchestration/service.py` so T046 passes
- [ ] T050 [US3] Write and pass scenario `tests/scenario/test_d4_rework_limit_escalation.py` (D-4)

**Checkpoint**: no run can wait forever; escalation is orchestrator-only.

---

## Phase 6: User Story 4 – Clarifications pause and resume the same run (P1)

**Goal**: an agent or reviewer asks a role; the answer resumes the same run without counting as rework.

**Independent test**: the stub agent raises one clarification at T2; it is answered; the same run resumes and `rework_count` stays 0 (D-9).

### Tests first

- [ ] T051 [P] [US4] Write failing unit tests in `tests/unit/orchestration/test_addressee.py`: no named role → the terminal's R role, else its whole-terminal A role, else its first A role in spec order (FR-023a), checked against the real T0–T9 specs
- [ ] T052 [P] [US4] Write failing integration tests in `tests/integration/orchestration/test_clarification.py`: a building-time clarification moves the run to `awaiting_clarification` with `return_state=building` and records the round (US4/AC1); a person without the addressed role raises `NotAuthorised` (US4/AC2); the first answer resumes the same run, a second answer raises `AlreadyAnswered` (FR-024); a third round with `max_clarification_rounds: 2` escalates with `clarification_limit` (US4/AC3); an unanswered round past `clarification_sla` escalates with `clarification_sla` (US4/AC4); a reviewer clarification returns to `reviewing` after the answer (US4/AC5); the answers reach the next `BuildContext.clarifications`; `rework_count` never changes

### Implementation

- [ ] T053 [US4] Implement the addressee rule in `src/adlc/orchestration/routing.py` and clarification effects in `src/adlc/orchestration/engine.py` (round rows, `return_state`, `clarification_sla` timer) so T051 and T052 pass
- [ ] T054 [US4] Implement `answer_clarification` with `AlreadyAnswered` in `src/adlc/orchestration/service.py`
- [ ] T055 [US4] Write and pass scenario `tests/scenario/test_d9_clarification.py` (D-9)

**Checkpoint**: all P1 stories pass.

---

## Phase 7: User Story 5 – Operational events and re-entry (P2)

**Goal**: T8 raises operational events, routed by its event routes; T9 re-enters at the change-class terminal; continuous review keeps running.

**Independent test**: with a use case at T8, raise `T8.event.drift`; a T9 run opens; pass it with `reentry_terminal: T2`; `T9.reentry.T2` opens T2 (D-7).

### Tests first

- [ ] T056 [P] [US5] Write failing integration tests in `tests/integration/orchestration/test_operational_events.py`: `raise_operational_event` with a name not raised by any monitor of the pinned T8 raises `UnknownEvent`; `T8.event.drift` opens T9 (US5/AC1); `T8.event.safety_breach` records its `immediate` actions on the T8 run and opens T5 (US5/AC2); a `then_when` that holds through the policy interface writes the follow-on event (for example `T7.rollback`), and one that does not writes nothing
- [ ] T057 [P] [US5] Write failing integration tests in `tests/integration/orchestration/test_reentry_and_continue.py`: a T9 pass resolves `${T9.change_impact_assessment.reentry_terminal}` from the artifacts and writes `T9.reentry.T2` which opens T2 (US5/AC3); a template that resolves to a terminal not in the change-class re-entry list refuses the decision; `alternative=<destination>` in the pass fields is honoured; a T8 pass routed to `continue` starts a `review_due` timer from `review_schedule` for the tier, and when it fires the next T8 review run opens (FR-018b, US5/AC4)

### Implementation

- [ ] T058 [US5] Implement `raise_operational_event` in `src/adlc/orchestration/service.py` and event-route handling (`immediate`, `then_when`, follow-on event) in `src/adlc/orchestration/router.py` so T056 passes
- [ ] T059 [US5] Implement template re-entry and `continue` (`review_due` timer created by the close after timers are cancelled; on fire the timer loop calls the router to open the next review run, not a signal to the closed run) in `src/adlc/orchestration/engine.py` and `src/adlc/orchestration/timers.py` so T057 passes
- [ ] T060 [US5] Write and pass scenario `tests/scenario/test_d7_drift_reentry.py` (D-7)

**Checkpoint**: the lifecycle is a loop, not a line.

---

## Phase 8: User Story 6 – Reliable delivery, restart safety and dead letters (P2)

**Goal**: at-least-once delivery, exactly-once processing, ordered per use case, dead letters with re-queue, restart safety.

**Independent test**: stop the orchestrator while a run awaits sign-off, start a new one, decide; routing continues (SC-004).

### Tests first

- [ ] T061 [P] [US6] Write failing integration tests in `tests/integration/orchestration/test_idempotency.py`: delivering every event twice (including concurrently from two workers) yields zero duplicate runs (SC-005, US6/AC2); an event for a terminal with an active run becomes `event_received` on that run, not a new run (US6/AC3)
- [ ] T062 [P] [US6] Write failing integration tests in `tests/integration/orchestration/test_dead_letter.py` using the router fault-injection hook: a failing delivery is retried after 10 s, 1 min, 5 min, 15 min (scaled), and the fifth failure sets `dead_lettered_at` with `last_error` truncated to 2,000 characters (SC-006, US6/AC4); `list_dead_letters` and `requeue` require `ADLC_DEADLETTER_ROLE`; `requeue` of a non-dead-lettered event raises `NotDeadLettered`; after re-queue the event is delivered exactly once and `events.dead_letter_action` records who and when (US6/AC5)
- [ ] T063 [P] [US6] Write failing integration tests in `tests/integration/orchestration/test_ordering.py`: events of one use case are processed in creation order; a retrying earlier event blocks later events of the same use case but not other use cases; a dead-lettered event unblocks them (US6/AC6)
- [ ] T064 [P] [US6] Write failing integration tests in `tests/integration/orchestration/test_restart.py`: for each waiting state (`blocked`, `awaiting_clarification`, `awaiting_sign_off`, `escalated`) a fresh engine, router and worker over the same database continue correctly after the expected signal (SC-004, US6/AC1); an automatic step whose lease expired (crash mid-build) is retried and counts toward `max_auto_retries`, then escalates with `retry_limit` (FR-030a); an agent result applied after a human terminated the run is discarded and recorded in `run.run_activity` with the original step (`build` or `review`) and outcome `stale` (FR-030b); timers overdue during downtime fire once

### Implementation

- [ ] T065 [US6] Add retries, the backoff schedule, dead-lettering, the fault-injection hook and `NOTIFY`-safe processing to `src/adlc/orchestration/outbox.py` so T062 and T063 pass
- [ ] T066 [US6] Add `list_dead_letters` and `requeue` with `NotDeadLettered` to `src/adlc/orchestration/service.py` (role from `OrchestratorSettings.deadletter_role`)
- [ ] T067 [US6] Add lease expiry handling, retry counting for interrupted steps and stale-result recording to `src/adlc/orchestration/engine.py` so T061 and T064 pass

**Checkpoint**: all six stories pass.

---

## Phase 9: Orchestrator process and Compose

- [ ] T068 Write failing tests in `tests/integration/orchestration/test_worker_process.py`: `Worker.run_once()` writes `events.orchestrator_heartbeat`; `adlc-orchestrator health` exits 0 with a fresh heartbeat and 1 when it is older than `ADLC_HEARTBEAT_MAX_AGE`; the loop wakes on `NOTIFY adlc_outbox` within one second and falls back to `ADLC_POLL_INTERVAL`; a close-to-next-open gap is ≤ 2 s at p95 over 50 closes (SC-003), with the measured p95 printed in the test output; under `CI=true` the threshold is relaxed to 5 s so a slow runner does not make it flaky, while the 2 s target is checked locally and in quickstart §4
- [ ] T069 Implement the long-running loop (`LISTEN`, wait, `drain`, heartbeat, graceful stop on SIGTERM) in `src/adlc/orchestration/worker.py` and the Typer entry point `run | health` in `src/adlc/orchestration/__main__.py`, wiring the real `SqlSpecRegistry` and the stubs, so T068 passes
- [ ] T070 Add the `orchestrator` service to `deploy/compose.yaml` (same image as `api`, command `adlc-orchestrator run`, `depends_on` `register` completed successfully, healthcheck `adlc-orchestrator health`, `adlc_app` credentials only) and show it in `make status`
- [ ] T071 Write `scripts/demo_drive.py`: drives `OrchestratorService` against the live database through the happy path, signing in as the scripted accounts from `ADLC_ACCOUNTS_FILE`, printing each run and its routing gap (quickstart §4)

---

## Phase 10: Polish and cross-cutting

- [ ] T072 [P] Extend `tests/unit/test_no_hardcoded_values.py` so `src/adlc/orchestration/` is checked for role ids from `adlc-specs/shared/roles.yaml` and destination names from `adlc-specs/shared/route_destinations.yaml`, as well as terminal ids and event names (constitution I)
- [ ] T073 [P] Write `src/adlc/orchestration/README.md` (states, signals, process loop, how 004 and 006 replace the stubs, settings) and update `tests/scenario/README.md` with the scenarios added
- [ ] T074 [P] Add the ADR-01 change note to `docs/build-plan.md` §8 and `docs/solution-architecture.md` §17: terminal runs use a PostgreSQL state machine behind `TerminalRun`, LangGraph stays for agent graphs (006); mark it "changed by 003, CoE to confirm" (research R-01)
- [ ] T075 Run the quickstart (`specs/003-lifecycle-orchestration/quickstart.md` §1–§4) including the 10-times scenario loop and the live stack; record the results in the PR description
- [ ] T076 Run `make check` (lint, typecheck, tests with the 80% core gate including `orchestration/`, migration check, secret scan) and fix any failure

---

## Dependencies and execution order

- **Phase 1 → Phase 2 → stories.** Phase 2 blocks everything.
- **US1** (Phase 3) blocks every other story: they all need open, advance, delivery and pass.
- **US2, US3, US4** depend only on US1 and can run in parallel. US3's scenario D-4 needs US2's rework counter (T041).
- **US5** needs US2 (decisions) and US3 (timers, for `continue`).
- **US6** needs US1; its restart tests cover the waiting states from US3 and US4, so run it after them.
- **Phase 9** needs US6 (the loop uses retries and dead letters). **Phase 10** is last.

Within a story: test tasks first (they must fail), then implementation, then the scenario.

## Parallel examples

- **Phase 2**: T008, T009, T010, T011, T012 together; then T013, T014, T016, T017, T020 together while T015 is written.
- **US1**: T023–T027 together; T028 and T031 can proceed in parallel after them.
- **US2**: T035–T040 together; T045's three scenario files together at the end.
- **US6**: T061–T064 together.

## Implementation strategy

1. **MVP**: Phases 1–3. Stop and run `tests/scenario/test_happy_path.py`: the lifecycle moves end to end.
2. **Demo moments**: Phases 4–6 add D-2, D-3, D-5, D-4 and D-9; Phase 7 adds D-7.
3. **Hardening**: Phase 8 (delivery and restart), Phase 9 (process and Compose), Phase 10.
4. Commit after each phase checkpoint with `make check` passing.
