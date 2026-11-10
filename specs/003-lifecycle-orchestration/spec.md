# Feature Specification: Lifecycle Orchestration

**Feature Branch**: `003-lifecycle-orchestration`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "Feature 003 lifecycle-orchestration. Build the lifecycle orchestration: every terminal T0–T9 runs the same flow driven only by its registered spec; events open runs, a durable run moves through nine states, outcomes route to the next terminal, closing writes the ledger record and the next event together, timers escalate, and stuck events are dead-lettered."

## Clarifications

### Session 2026-11-10

- Q: Does an exception route immediately or after a separate waiver approver approves? → A: Two steps: the owner proposes, the waiver approver (the exception's `set_by` role, else the terminal's A) approves or rejects.
- Q: Where does the run activity table come from? → A: This feature creates it and writes a row for every run step; feature 005 adds views and KPI queries.
- Q: What happens to a run that stays blocked? → A: `escalate_after` applies to blocked runs too (trigger "timer"); the accountable owner can supply the evidence or terminate, and the owner may terminate a blocked run at any time.

**Source sections**: build plan §6 (row 003), §8 (worked example); SA §6.1–§6.4, §8.1, §10, Annex A.3, A.5; TDS §3 (outcome statuses), Annex C.2 (TERMINAL_RUN, OUTBOX_EVENT, LEDGER_RECORD); feature 002 (registry, routing data); constitution I, III, V, VII, IX, X, XII.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A submitted use case opens T0 and flows terminal to terminal (Priority: P1)

A business owner submits a use case. The platform:

- creates the use case (`UC-nnnn`);
- pins the active version of every terminal spec for it;
- opens a T0 run.

Each run then moves through its states as the work happens. Each state change follows the
pinned spec, never code:

1. Prerequisites are checked.
2. The (stub) agent builds the artifacts.
3. Automated controls are checked.
4. The (stub) reviewer recommends an outcome.
5. Humans sign off.

When the run closes with `pass`, the next terminal opens through the outcome event. A full
T0→T9 path completes with stub agents.

**Why this priority**: this is the engine every later feature plugs into. Without it there is
no lifecycle to demonstrate (D-1, and the base for D-2 to D-9).

**Independent Test**: submit a use case with stub agents that always produce valid artifacts.
Pass every terminal as its owner. Confirm one closed run per terminal T0–T8, each opened by
the previous terminal's pass event. Confirm T9 then opens on a T8 event and closes the
lifecycle (pass to `lifecycle_closed`).

**Acceptance Scenarios**:

1. **Given** registered specs, **When** a business owner submits a use case, **Then** a use
   case record exists with an id `UC-nnnn`, every terminal's active spec version is pinned for
   it, and a run `UC-nnnn/T0/run-1` is open.
2. **Given** a run whose prerequisites hold, **When** it starts, **Then** it moves
   opened → building → checking → reviewing → awaiting_sign_off, and each move is recorded
   with time and actor.
3. **Given** a run awaiting sign-off, **When** every required approver passes it, **Then** the
   run closes with status `pass`, its ledger record and the event `T<n>.pass` are written
   together, and the run of the next terminal opens within 2 seconds.
4. **Given** a run whose prerequisite is unmet with `on_missing: block`, **When** it opens,
   **Then** it waits in `blocked` and is re-checked when new evidence arrives for the use case.
   With `on_missing: warn`, it proceeds with a warning recorded.
6. **Given** a blocked run, **When** its `escalate_after` passes, **Then** it escalates with
   trigger "timer". **When** an owner holding a terminate right terminates it at any time,
   **Then** it closes with `terminate`.
5. **Given** a run whose blocking control fails, **When** controls are checked, **Then** the
   run returns to `building` without counting as rework, up to the terminal's retry limit.

---

### User Story 2 - Human decisions route the lifecycle, including rework by root cause (Priority: P1)

A terminal owner decides a run awaiting sign-off:

- **pass**;
- **rework**, with a mandatory comment and root cause;
- **exception**, with waiver owner, expiry and compensating control;
- **terminate**, with a reason.

The lifecycle follows the pinned spec's outcome model. Rework goes to the root-cause
terminal, and the new run's context carries the comment, the defect evidence and the previous
artifacts, so the agent fixes rather than rebuilds.

**Why this priority**: D-2 (rejection with comment, then rework using it) and D-3 (a T4 defect
returns to T3) are core demo moments.

**Independent Test**: at T1, reject with a comment and root cause `requirement`. A new T1 run
opens whose context includes the comment, and the rework counter for T1 is 1. At T4, rework
with root cause `implementation`: a new T3 run opens with the defect log in its context.

**Acceptance Scenarios**:

1. **Given** a run awaiting sign-off, **When** an owner chooses rework without a comment or
   root cause, **Then** the decision is refused and the run stays where it is.
2. **Given** a T4 run awaiting sign-off, **When** the owner reworks it with root cause
   `implementation`, **Then** the run closes with the event `T4.rework.implementation`, a new
   T3 run opens, and its context holds the comment, the T4 defect log reference and the
   previous T3 artifacts reference.
3. **Given** a terminal whose `sign_off.min_approvers` is 2, **When** one approver passes,
   **Then** the run keeps waiting. **When** a second, different approver passes, **Then** it
   closes.
4. **Given** an approver's decision that differs from the reviewer's recommendation, **When**
   it is submitted without a reason, **Then** it is refused (SA §8.2).
5. **Given** a person who does not hold a sign-off role for that terminal, **When** they
   submit a decision, **Then** it is refused. Agents and the reviewer can never submit an
   outcome (constitution III).
6. **Given** an owner terminates a run with a reason, **Then** the run closes with
   `terminate`, the use case lifecycle stops, and the outcome's `notify` roles are recorded as
   notified.
7. **Given** an exception decision with waiver owner, expiry and compensating control,
   **Then** a waiver is proposed with the terminal's `recheck_at` list and the run waits for
   the waiver approver. **When** the approver approves, **Then** the run closes with
   `exception` and the lifecycle continues per the exception route. **When** the approver
   rejects, **Then** the waiver is rejected and the run returns to `awaiting_sign_off`.

---

### User Story 3 - Escalation after limits and human completion (Priority: P1)

The orchestrator moves a run to `escalated` when any of these happens:

- the rework count for the use case and terminal exceeds `max_rework_cycles`;
- the escalation timer (`escalate_after`) passes;
- clarification rounds or the clarification SLA are exceeded;
- the agent run exceeds its budget.

The accountable human completes the artifacts, and the run continues to sign-off.

**Why this priority**: D-4 (escalation after 3 rework cycles). It also bounds every run, so
none can loop forever.

**Independent Test**: rework T1 three times. On the fourth rework the new T1 run opens
directly in `escalated`. A human completes the artifacts, and the run reaches
`awaiting_sign_off`.

**Acceptance Scenarios**:

1. **Given** a terminal with `max_rework_cycles: 3`, **When** a fourth rework arrives for the
   same use case and terminal, **Then** the new run is `escalated`, with trigger "rework
   limit" recorded, and the escalate route (for example `human_completion`) is applied.
2. **Given** a run whose `escalate_after` (resolved for the use case's risk tier) passes while
   it is not closed, **Then** it moves to `escalated`, with trigger "timer" recorded.
3. **Given** an escalated run, **When** the accountable owner submits the completed artifacts,
   **Then** the run moves to `awaiting_sign_off` and is decided as usual.
4. **Given** any actor other than the orchestrator, **When** it tries to set `escalate`,
   **Then** the attempt is refused.

---

### User Story 4 - Clarifications pause and resume the same run (Priority: P1)

An agent (or the reviewer) that lacks information pauses its run with questions addressed to
a role, stating where it looked. A human of that role answers. The same run resumes with the
answer in its context. Clarifications never count as rework and never change routing.

**Why this priority**: D-9 (clarification asked, answered, same run resumes, not counted as
rework).

**Independent Test**: let the stub agent raise one clarification at T2. The run waits in
`awaiting_clarification`. Answer it as the addressed role. The same run id resumes to
`building`, the answer is in its context, and the T2 rework counter is still 0.

**Acceptance Scenarios**:

1. **Given** a building run, **When** the agent raises a clarification without naming a role,
   **Then** it is addressed to the terminal's R role, or the A role when no R exists (SA §8.1).
2. **Given** an open clarification, **When** a person who does not hold the addressed role
   answers, **Then** the answer is refused.
3. **Given** a terminal with `max_clarification_rounds: 2`, **When** a third clarification is
   raised in the same run, **Then** the run escalates, with trigger "clarification limit".
4. **Given** an open clarification older than `clarification_sla`, **Then** the run escalates,
   with trigger "clarification SLA".
5. **Given** the reviewer raises a clarification while reviewing, **When** it is answered,
   **Then** the run returns to `reviewing`, not to `building`.

---

### User Story 5 - Operational events and re-entry (Priority: P2)

T8 raises an operational event (for example drift). The lifecycle routes it per T8's event
routes: immediate actions are recorded, the run of the routed terminal opens (for example T9),
and T9's decision re-enters the lifecycle at the terminal named by the change class in its
assessment (for example T2).

**Why this priority**: D-7. It depends on US1 and US2 working.

**Independent Test**: with a use case at T8, raise `T8.event.drift`. A T9 run opens. Pass it
with a change impact assessment naming re-entry `T2`: the event `T9.reentry.T2` is emitted
and a new T2 run opens.

**Acceptance Scenarios**:

1. **Given** a running T8, **When** `T8.event.drift` is raised, **Then** a T9 run opens for
   the use case with the event as its trigger evidence.
2. **Given** `T8.event.safety_breach`, **Then** its immediate actions are recorded and a T5 run
   opens.
3. **Given** a T9 run passed with `reentry_terminal: T2`, **Then** `T9.reentry.T2` is emitted
   and T2 opens. With the alternative `lifecycle_closed`, the use case lifecycle closes
   instead.
4. **Given** a T8 review period, **When** its review is passed, **Then** the route `continue`
   keeps T8 running into the next review period rather than opening another terminal.

---

### User Story 6 - Reliable delivery, restart safety and dead letters (Priority: P2)

Events are delivered at least once and processed exactly once per event id. Runs survive a
restart of the orchestrator. An event that cannot be delivered after 5 attempts is
dead-lettered with its error. The CoE can list dead letters and re-queue one after a fix.

**Why this priority**: NFR-02 and SA §6.4. They make the demo safe, but the flow works
without them.

**Independent Test**: stop the orchestrator while a run waits for sign-off, restart it, and
decide the run; it closes correctly. Deliver the same event twice: one run opens. Make a
subscriber fail 5 times: the event is dead-lettered; fix it and re-queue: it is delivered.

**Acceptance Scenarios**:

1. **Given** runs in every waiting state, **When** the orchestrator restarts, **Then** each run
   is in the same state with the same data, and continues on the next signal or timer.
2. **Given** an event delivered twice, **Then** the second delivery is ignored.
3. **Given** an event for a terminal that already has an active run for the use case,
   **Then** it is delivered to that run as a signal, and no second run opens.
4. **Given** a delivery that fails, **Then** it is retried with increasing delays. After the
   fifth failure it is dead-lettered, with the last error and the attempt count recorded.
5. **Given** a dead-lettered event, **When** the CoE re-queues it, **Then** it is delivered
   again, and the re-queue is recorded with who did it and when.
6. **Given** events for one use case, **Then** they are processed in the order they were
   written.

---

### Edge Cases

- A rework root cause that the terminal's outcome model does not route: the decision is
  refused, and the allowed causes are listed.
- Rework to the special destination `owning_terminal` (T6 missing evidence): the owning
  terminal is taken from the decision (the human names it); a decision without it is refused.
- An escalation route that is a board or role destination (for example `release_board`): the
  run stays `escalated` and is completed by the accountable owner, with the destination
  recorded.
- The T9 pass route template names a terminal that is not a change-class re-entry: the decision
  is refused.
- An exception on a terminal with `exception.not_allowed` (T7): refused.
- A terminal that both an outcome route and a trigger subscription lead to: it opens once (the
  event is the single path; routes are checked against subscriptions by 002 rule V-17).
- An event arrives for a terminated or closed lifecycle: it is recorded and ignored.
- A spec version is deprecated while a use case runs: the use case keeps its pinned versions.
- Two decisions for the same run arrive at the same time: one wins and the other is refused as
  stale.
- The orchestrator stops in the middle of closing a run: the ledger record and the outcome
  event exist both or neither.
- A timer fires for a run that has already closed: ignored.
- Clock skew or long downtime: overdue timers fire once on restart, not once per missed tick.

## Requirements *(mandatory)*

### Functional Requirements

**Use cases and runs**

- **FR-001**: Submitting a use case MUST create a use case record with the next id `UC-nnnn`,
  the submitter as business owner, the free-text intake, and status `active`. It MUST pin the
  active version of every terminal spec for that use case, and emit `usecase.submitted`.
- **FR-002**: A run MUST be identified as `<usecase_id>/T<n>/run-<k>`, where `k` counts runs of
  that terminal for that use case (SA Annex A.5). It MUST record the pinned spec version, the
  triggering event, its state, opened and due times, and its rework count at open.
- **FR-003**: At most one run per use case and terminal MUST be active (not closed) at a time.
  An event for a terminal with an active run MUST be delivered to that run as a signal.
- **FR-004**: A run MUST follow the nine states and transitions of SA §6.2. Every transition
  MUST be recorded with from-state, to-state, actor type, actor id, reason and time.

**Flow inside a run (generic for every terminal)**

- **FR-005**: On open, prerequisites MUST be evaluated through the policy interface, using the
  pinned spec. Unmet `block` prerequisites hold the run in `blocked`; unmet `warn`
  prerequisites are recorded and the run proceeds.
- **FR-006**: The run MUST ask the agent interface to build the artifacts listed in the pinned
  spec, giving it a context that includes: the spec, the use case, the trigger evidence (rework
  comment, root cause, defect evidence, previous artifacts), and any clarification answers so
  far.
- **FR-007**: Automated controls MUST be evaluated through the policy interface. A failed
  blocking control returns the run to `building` (an automated retry, not rework), up to the
  spec's `max_auto_retries`; beyond that the run escalates.
- **FR-008**: The reviewer interface MUST produce a recommendation and checklist scores before
  sign-off; the recommendation is recorded and shown with the decision.

**Human decisions and outcome rights (constitution III)**

- **FR-009**: Only a person holding one of the terminal's sign-off roles (including the
  applicable tier or mode rule) may decide pass, rework, exception or terminate. Terminate is
  limited further to the outcome's `set_by` roles when given.
- **FR-009a**: A person allowed to terminate MAY terminate a run in `blocked`, `escalated` or
  `awaiting_sign_off`, with a reason.
- **FR-010**: Rework MUST require a comment and a root cause from the terminal's
  `route_by_root_cause` (or any cause when only a plain route exists). Exception MUST require
  the outcome's `requires` fields. Terminate MUST require a reason.
- **FR-011**: `pass` MUST close the run only when `min_approvers` distinct approvers have
  passed. A rework, exception or terminate decision by an authorised approver closes the run
  immediately.
- **FR-012**: A decision that differs from the reviewer's recommendation MUST include a reason.
- **FR-012a**: An exception MUST take two steps (TDS §3 "Owner + waiver approver"; SA §8.1).
  The owner proposes it with the required waiver fields; the waiver approver approves or
  rejects it. The approver is the exception outcome's `set_by` role when the spec gives one
  (for example `risk_owner` on T5), otherwise the terminal's A role. The approver must be a
  different person from the proposer. Approval closes the run with `exception`; rejection
  returns the run to `awaiting_sign_off`.
- **FR-013**: Escalate MUST be set only by the orchestrator. Agents and the reviewer MUST NOT
  set any outcome.

**Routing (only from pinned specs, through the read interface of feature 002)**

- **FR-014**: Closing a run MUST emit its outcome event: `T<n>.pass`, `T<n>.exception`,
  `T<n>.rework.<root_cause>`, `T<n>.escalate` or `T<n>.terminate`. Event payloads carry the use
  case id, correlation id `<usecase_id>/lifecycle`, causation id (the closing run id) and
  ledger references, never artifacts.
- **FR-015**: An event MUST open a run of every terminal whose pinned spec subscribes to it. A
  terminal whose pinned spec does not subscribe MUST NOT open, whatever the outcome route
  says.
- **FR-016**: Special destinations MUST be handled generically by kind (feature 002
  `route_destinations.yaml`):
  - `human` keeps the run escalated for human completion;
  - `terminal_resolver` takes the terminal named in the decision;
  - `terminating` closes the use case lifecycle;
  - `continue` keeps a continuous terminal running;
  - `external` is recorded as handed off.
- **FR-017**: T8 operational events MUST route per the pinned T8 `event_routes`, recording
  immediate actions and applying conditional follow-ons when their condition holds.
- **FR-018**: A pass whose route is a template MUST resolve it from the run's artifacts (T9:
  the change impact assessment's re-entry terminal), and emit the matching re-entry event, or
  the alternative destination when the decision chooses it.

**Counters and timers**

- **FR-019**: The rework count per use case and terminal MUST increase by one for each rework
  routed to that terminal. Automated retries and clarifications MUST NOT change it.
- **FR-020**: Opening a run with a rework count above the terminal's `max_rework_cycles` MUST
  put it in `escalated`.
- **FR-021**: Timers MUST be taken from the pinned spec's timeline for the use case's risk tier
  (unknown tier before T0 closes: the `medium` values; T0 uses its own tier-independent
  values). Passing `escalate_after` escalates the run in any open state, including `blocked`,
  and passing `clarification_sla` on an open clarification escalates it. A configurable time scale MUST shorten all timers for the
  demo.
- **FR-022**: Escalation MUST record its trigger: rework limit, timer, clarification limit,
  clarification SLA, retry limit or budget.

**Clarifications**

- **FR-023**: An agent or the reviewer MUST be able to raise a clarification round of one or
  more questions, with the addressed role and where it looked. The run waits in
  `awaiting_clarification`.
- **FR-024**: Only a person holding the addressed role may answer. The answer resumes the same
  run in the state it came from (`building` or `reviewing`) and is added to its context.
- **FR-025**: Each round MUST be recorded with id `<run_id>/clar-<k>`, questions, addressee,
  answers, and asked and answered times. Rounds beyond `max_clarification_rounds` escalate the
  run.

**Closing, ledger and outbox (constitution V)**

- **FR-026**: Closing a run MUST write, in one transaction: the run's final status, its ledger
  record (baseline table from feature 001: key `<usecase_id>/T<n>/run-<k>`, content hash of the
  record content, hash of the previous record of the use case), and the outcome event in the
  outbox.
- **FR-027**: The ledger record content MUST include: the spec version and hash, the decision
  and deciders, the reviewer recommendation, artifact references, control results,
  clarification rounds, and for exceptions the waiver.

**Delivery and reliability**

- **FR-028**: A poller MUST deliver outbox events to the router in write order per use case.
  Each event id is processed once (idempotency record). Failures are retried with increasing
  delays (10 s, 1 min, 5 min, 15 min); after 5 failed attempts the event is dead-lettered with
  its last error.
- **FR-029**: The CoE MUST be able to list dead-lettered events and re-queue one. The re-queue
  is recorded with person and time, and resets the attempt count.
- **FR-030**: Run state MUST be durable. After a restart, every run continues from its last
  recorded state; overdue timers fire once.
- **FR-031**: Routing a closed run's outcome to the next run's open MUST take at most 2 seconds
  under normal load (NFR-04).

**Interfaces and stubs (constitution VII)**

- **FR-032**: Prerequisite evaluation, control evaluation and permission checks MUST go through
  a policy interface. This feature provides a stub implementation: configurable per test, all
  true by default.
- **FR-033**: Building artifacts and reviewing MUST go through agent and reviewer interfaces.
  This feature provides stubs that produce schema-shaped placeholder artifacts, and that can
  be scripted to raise a clarification, fail a control, or exceed a budget.
- **FR-034**: Human actions MUST be offered as orchestrator service operations: submit use
  case, decide, answer clarification, complete escalated run, raise operational event (T8),
  list and re-queue dead letters. The HTTP and inbox front end for them is feature 007.

**Observability (constitution X)**

- **FR-035**: Every run step MUST write an activity record (actor type, actor id, step, start,
  end, outcome) from this feature on (constitution X). This feature creates the run activity
  record store; feature 005 adds views and KPI queries over it. Every agent, reviewer and
  policy call MUST be traced with the run id.
- **FR-036**: Orchestration code MUST contain no terminal-specific values or branching
  (constitution I). Every difference between terminals comes from the pinned spec.

### Key Entities

- **Use case**: id `UC-nnnn`, name, business owner, risk tier (set when T0 passes), status
  (`active`, `terminated`, `closed`), created time.
- **Spec pin**: use case, terminal, pinned version (feature 002 table; written here).
- **Terminal run**: run id, use case, terminal, run version, pinned spec version, trigger event,
  state, recommended status, final status, rework count, opened, due, closed times.
- **Run transition**: run, from-state, to-state, actor type and id, reason, time.
- **Sign-off**: run, role, person, decision, comment, root cause, reason when differing from
  the recommendation, time.
- **Waiver**: id `WVR-nnnn`, run, owner, expiry, compensating control, recheck terminals,
  status (`proposed`, `approved`, `rejected`, `expired`), proposed by, decided by.
- **Run activity**: run, step, actor type, actor id, start, end, outcome. One record per step;
  the source for the activity feed and time KPIs (SA §12.1).
- **Clarification round**: id `<run_id>/clar-<k>`, questions, addressed role, where the asker
  looked, answers, answered by, asked and answered times.
- **Outbox event**: event id (time-ordered), type, use case, correlation id, causation run id,
  payload (references only), attempts, next attempt time, processed time, dead-lettered time,
  last error.
- **Processed event**: event id, processed time (idempotency).
- **Ledger record (baseline)**: key, content hash, previous record hash, written time; content
  stored by reference until feature 005 adds the full record.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A full T0→T9 lifecycle with stub agents and scripted human decisions completes,
  with exactly one closed run per terminal and zero manual database steps.
- **SC-002**: Demo moments D-2, D-3, D-4, D-7 and D-9 each run end to end as automated
  scenarios with stub agents, and each passes 10 out of 10 times.
- **SC-003**: The time from a run's close to the next run's open is at most 2 seconds in 95% of
  routings, measured over a full lifecycle.
- **SC-004**: After an orchestrator restart in each waiting state (blocked,
  awaiting_clarification, awaiting_sign_off, escalated), 100% of runs continue correctly.
- **SC-005**: Delivering every event twice yields zero duplicate runs.
- **SC-006**: An event whose delivery always fails is dead-lettered after exactly 5 attempts,
  and after a fix and re-queue it is delivered once.
- **SC-007**: 100% of closed runs have a ledger record and an outcome event written together;
  zero closed runs exist without both.
- **SC-008**: 100% of attempts by agents or the reviewer to set an outcome, and of decisions by
  people without the role, are refused.

## Assumptions

- Real agents, the reviewer and the context builder arrive in feature 006; this feature's stubs
  implement the same interfaces.
- Real CEL evaluation and permission checks arrive in feature 004; this feature's policy stub
  implements the same interface.
- HTTP endpoints and the inbox for human actions are feature 007; this feature exposes service
  operations that 007 calls.
- The ledger hash chain is written in its baseline form (key, content hash, previous hash). The
  full record schema, artifact store and verification arrive in feature 005.
- The risk tier is known once T0 passes (T0 emits `risk_tier`). Before that, timers use the
  `medium` tier.
- Reminders before escalation are optional for the MVP (build plan simplify-if-late); if built,
  they are recorded as notifications.
- Email and in-app notification delivery are feature 007; this feature records whom to notify.
- The demo uses a time scale setting so that day-long timers run in seconds or minutes.
- One orchestrator process runs in the MVP. Restart safety is required; running several at
  once is post-MVP (SA §16).
