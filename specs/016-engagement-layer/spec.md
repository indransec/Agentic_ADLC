# Feature Specification: Engagement Layer (board ↔ platform)

**Feature Branch**: `016-engagement-layer`

**Created**: 2026-11-20

**Status**: Draft

**Input**: User description: "016-engagement-layer (Phase 2 Option A, SA §22.3–22.4, build plan §11).
Make the tracker (the ADO simulator from feature 015, later real Azure DevOps) a way for people to
drive the lifecycle the inbox drives today, with the platform's backend as built: the orchestrator,
policy engine, ledger and agents are reused unchanged and stay the only source of truth; the board
is a view and an input channel. Deliver a board-neutral port with one ADO adapter, the tracker
mapping and its validation, the outbound projector, inbound sync by polling revisions, manual
reconciliation, the sync tables and sync-health data, and a contract suite against the simulator.
Out of scope: the board, backlog and form UI (017, 018), the operations console (019), the demo on
the board (020), work plans, hold points and increments (Option B), webhooks, scheduled
reconciliation and a real ADO organisation."

## Clarifications

### Decided before this feature (recorded for context)

- Phase 2 Option A: the board becomes the user interface while the platform's lifecycle logic
  stays as built; the platform is the only source of truth for lifecycle state and the board is a
  view and an input channel (SA §22.1, decisions of 2026-11-20).
- Every human decision on the board goes through **one decision field** (`Custom.AdlcDecision`),
  saved with its comment. The Epic's column and sub-stage are written only by the platform's
  service account; a column moved by a person is reverted (SA §22.3, decided 2026-11-15,
  confirmed 2026-11-20).
- Registering a use case from the board emits the existing `usecase.submitted`; no
  `usecase.registered` event is added (SA §22.10).
- Inbound changes are read by polling revisions, not webhooks; reconciliation is manual only (a
  person starts it), no schedule (SA §22.3, decisions of 2026-11-18).
- Board users map to platform accounts through the accounts file and `roles.yaml`; there is no
  user-role table (decision of 2026-11-18).
- The tracker adapter lives inside the platform behind the `BoardAdapter` interface; there are no
  plug-in packages (decision of 2026-11-18; constitution VII as proposed in 1.2.0).
- The simulator (feature 015) is the only reference for the ADO contract until a real ADO
  organisation is available; the contract suite is run against real ADO before a real tracker is
  connected (SA §22.2 fidelity rule).
- Polling for changes uses the simulator's guarantee found in 015 (research R-06): query
  "changed at or after the previous answer's `asOf`", read each returned item's updates, and
  de-duplicate by work item and revision.

### Session 2026-11-20

- Q: How does a person enter the inputs a decision needs beyond its value and comment (root cause,
  reason, rework target, emitted values)? → A: all three ways: dedicated board fields; or, when a
  field is empty, a fixed `<input>: <value>` line in the decision comment (the field wins on a
  difference); and the console remains available for every decision.

## User Scenarios & Testing *(mandatory)*

The actors are the people who sign off, answer clarifications and propose or approve waivers in
the inbox today (the roles of `adlc-specs/shared/roles.yaml`), the CoE lead who runs
reconciliation, and the platform itself (its service account on the board). The board is the
simulator from feature 015; its screens arrive in 017 and 018, so in this feature people's board
actions are made through the simulator's API (as the board UI will make them) and observed through
it.

### User Story 1 – See the lifecycle on the board (Priority: P1)

A person opens the board and sees every use case as an Epic, in the column of its current
terminal, with the run's state as its sub-stage; under it, one item per terminal run and one item
per clarification round. The board follows the platform as the lifecycle moves, whether the
decisions are made on the board or in the inbox.

**Why this priority**: nothing can be decided on the board until the board shows what the
platform knows; it is also the half that can never change platform state, so it is the safest
first increment.

**Independent Test**: submit a use case in the inbox and let it run to its first sign-off; the
board holds one Epic in the first terminal's column with sub-stage "awaiting sign-off", one run
item with a link to the run's evidence, and the Epic and items carry the platform's ids; each
later transition appears on the board.

**Acceptance Scenarios**:

1. **Given** a use case submitted in the inbox, **When** the platform records it, **Then** an Epic
   appears on the board with the use case's name and intake text, the use case id, the first
   terminal's column and the sub-stage of its first run's state.
2. **Given** a run that opens, changes state or closes, **When** the platform records the change,
   **Then** the Epic's column and sub-stage and the run item's state are updated to match, by the
   platform's service account only.
3. **Given** a run that waits for a decision, **When** it is projected, **Then** its item shows the
   decision values the person may choose (the run's decision form), the fields that decision needs,
   the reviewer's recommendation, and a link to the run's evidence in the platform.
4. **Given** a clarification round, **When** it is asked, **Then** a clarification item appears
   under the run's item with the questions, the role it is addressed to and an empty answer field.
5. **Given** a decision made in the inbox, **When** it is accepted, **Then** the board shows it as
   though it had been made on the board (state, comment with who decided and when).
6. **Given** the board is unreachable, **When** platform changes happen, **Then** nothing in the
   platform waits or fails; the updates are delivered in order when the board is back, and after
   the retry limit an update is dead-lettered where the CoE can see and requeue it.

---

### User Story 2 – Decide a run from the board (Priority: P1)

A person who holds a role that may decide a run awaiting sign-off sets the run item's decision
field to `pass`, `rework`, `exception` or `terminate`, with a comment and any input the decision
needs, and saves. The platform treats the save as a request: it checks the person's decision
right and the decision's rules exactly as the inbox does, applies it if accepted, and writes the
result back to the board.

**Why this priority**: this is the point of the feature; it replaces the inbox's main action.

**Independent Test**: with a run awaiting sign-off, set its decision field to `pass` as an
approver; the run closes (or waits for the next required approver), the ledger records the
sign-off by that person, and the board moves the Epic to the next terminal's column. Repeat with
`rework` and no comment: refused, the field is cleared and a comment on the item gives the reason.

**Acceptance Scenarios**:

1. **Given** a run awaiting sign-off and a person holding a still-needed sign-off role, **When**
   they save `pass` with a comment, **Then** the platform records their approval exactly as an
   inbox approval (decision log, run activity, ledger when the run closes), and the board shows
   the run's new state.
2. **Given** a run needing two approvals, **When** the first approver saves `pass`, **Then** the
   approval is recorded, the platform clears the decision field and comments "approved by <name>,
   waiting for <roles>", and the second approver can save `pass` again.
3. **Given** a decision that needs a root cause, reason, rework target or typed value, **When** it is
   given in its board field, or (field empty) as a `<input>: <value>` line in the comment, **Then**
   it is accepted as in the inbox; a field and a differing comment line → the field is used and the
   reply comment says so.
4. **Given** a decision that needs a comment, root cause, reason, rework target or typed value,
   **When** it is saved without it, **Then** it is refused with the same reason the inbox gives, the
   item's decision inputs are reverted and a comment states the reason.
5. **Given** a decision by a person whose mapped roles do not allow it, **When** it is saved,
   **Then** it is refused for decision rights, reverted, and the reason is commented (D-12).
6. **Given** the same board change read twice (an overlapping poll, a restart), **When** it is
   processed again, **Then** it has no second effect: each board update (work item id and update
   number) becomes at most one platform command.
7. **Given** a decision saved on a run that has meanwhile moved on (decided in the inbox, or a new
   run version), **When** it is processed, **Then** it is refused as stale and reverted with that
   reason.

---

### User Story 3 – Register a use case from the board (Priority: P1)

A person creates an Epic on the board with a name and an intake description. The platform
registers it as a use case (the same submission as the inbox), links the Epic to the new use case
and starts its lifecycle.

**Why this priority**: without it the board cannot start a lifecycle and the inbox stays
necessary for every demo.

**Independent Test**: create an Epic as a mapped person in the board's use-case area; within one
polling interval the platform holds a new use case submitted by that person with that name and
intake text, the Epic carries its use case id and sits in the first terminal's column.

**Acceptance Scenarios**:

1. **Given** a mapped person who may submit use cases (the same roles as in the inbox: an
   accountable role of the terminals a submission opens), **When** they create an Epic with a title
   and description in the mapped area, **Then** the platform registers one use case with that
   name and intake text, submitted by that person, emitting `usecase.submitted`.
2. **Given** that Epic, **When** registration succeeds, **Then** the platform writes the use case id
   and moves the Epic to the first terminal's column; the person's own column choice is not used.
3. **Given** an Epic with an empty description, or created by an unmapped user, **When** it is
   read, **Then** no use case is registered and a comment on the Epic gives the reason; the Epic is
   left for the person to fix (editing it is read as a new request) or remove.
4. **Given** an Epic the platform itself created (a use case submitted in the inbox), **When** it is
   read, **Then** it is not registered again.

---

### User Story 4 – Answer a clarification from the board (Priority: P2)

The person holding the role a clarification round is addressed to fills the answer field of the
clarification item and saves. The platform records the answers and the run continues, as when
answered in the inbox.

**Why this priority**: clarifications stop runs until answered; answering them on the board keeps
the person in one place.

**Independent Test**: with a run awaiting clarification, save answers on its clarification item
as the addressed role; the run leaves "awaiting clarification", the answers are recorded under
that person, and the item shows as answered.

**Acceptance Scenarios**:

1. **Given** an unanswered round addressed to a role the person holds, **When** they save one
   answer per question (numbered as the questions are), **Then** the platform records them as that
   person's answers and the run continues.
2. **Given** a person who does not hold the addressed role, or an answer count that does not match
   the questions, **When** they save, **Then** it is refused, the answer field is cleared and the
   reason is commented.
3. **Given** a round already answered (in the inbox or on the board), **When** another answer is
   saved, **Then** it is refused as already answered and reverted.

---

### User Story 5 – Waivers, escalations and termination from the board (Priority: P2)

A person proposes an exception (a waiver) by deciding `exception` with its reason; a waiver
approver then approves or rejects it on the same run item. When a run is escalated, a person with
the accountable role completes the escalation from the board. A blocked or waiting run can be
terminated with a reason.

**Why this priority**: these decisions exist in the inbox today; without them a demo on the board
falls back to the inbox at the first exception or escalation.

**Independent Test**: decide `exception` with a reason as an approver; the run shows the pending
waiver; a different person holding a waiver-approver role saves `approve waiver`; the waiver is
recorded and the run proceeds as the inbox would make it. Escalate a run (timer) and complete it
from the board as the accountable role; it returns to awaiting sign-off.

**Acceptance Scenarios**:

1. **Given** a run awaiting sign-off, **When** a person saves `exception` with a reason, **Then** a
   waiver is proposed as in the inbox and the run item shows it as pending with the approver roles.
2. **Given** a pending waiver, **When** a person who may approve it and did not propose it saves
   `approve waiver` or `reject waiver` with a comment, **Then** the platform records the decision and
   the board follows; the proposer saving it is refused (separation of duties).
3. **Given** an escalated run, **When** a person holding the terminal's accountable role saves
   `complete escalation`, **Then** the run returns to awaiting sign-off with its current artifacts
   (artifact edits stay in the platform's console).
4. **Given** a run that may be terminated, **When** a person with that right saves `terminate` with a
   reason, **Then** the run and its use case close as in the inbox; without a reason it is refused.

---

### User Story 6 – The board cannot get ahead of the platform (Priority: P2)

People can change anything on the board, but only the platform decides lifecycle state. A person
who drags an Epic to another column, edits the sub-stage or a platform-written field, or decides
without being a mapped user sees the change reverted with a comment giving the reason (D-12).

**Why this priority**: it is what makes the board safe to use as the interface; it is also
demo moment D-12.

**Independent Test**: as a mapped person, change an Epic's state to a later terminal's column;
within one polling interval the column is back and a comment names the rule. As an unmapped board
user, set a decision; it is reverted with "unknown user".

**Acceptance Scenarios**:

1. **Given** an Epic, **When** a person changes its column (state), sub-stage or any field the
   mapping marks platform-written, **Then** the platform restores the field and comments why.
2. **Given** a board user with no mapped account, **When** they make any change that would be a
   request, **Then** it is refused before any decision right is checked, reverted, and commented
   ("not a mapped platform user").
3. **Given** a change to a field the mapping neither marks platform-written nor reads (for example a
   tag), **When** it is read, **Then** it is ignored: no command, no revert.
4. **Given** a revert, **When** it is written, **Then** it is written by the service account, so the
   next poll does not read it as a person's change.

---

### User Story 7 – Reconcile the board with the platform (Priority: P2)

The CoE lead starts a reconciliation (command line or API). The platform compares every linked
item with its own state, corrects the board where they differ (the platform wins), creates
missing items, and reports the drift it found and fixed (D-13).

**Why this priority**: polling and the outbox make drift rare, not impossible (a board outage
past the retry limit, a manual edit by an administrator, a restored database). It is demo moment
D-13 and the way to put existing use cases on the board.

**Independent Test**: change three things on the board directly (an Epic's column, a run item's
state, a deleted clarification item) by a means the sync ignores; run reconciliation; the report
lists the three differences and the board matches the platform afterwards; a second run reports
no drift.

**Acceptance Scenarios**:

1. **Given** linked items that differ from the platform, **When** reconciliation runs, **Then**
   each difference is corrected on the board and listed in the report (item, field, board value,
   platform value).
2. **Given** use cases or runs with no board item (for example from before this feature), **When**
   reconciliation runs, **Then** their items are created and linked.
3. **Given** a person without the CoE role (the role named by `ADLC_DEADLETTER_ROLE`, the same
   role that sees dead letters), **When** they start reconciliation, **Then** it is
   refused.
4. **Given** reconciliation, **When** it runs, **Then** it never changes platform state: it reads
   the platform and writes only to the board.

---

### User Story 8 – A validated tracker mapping (Priority: P2)

Everything tracker-specific (item types, states and columns, the sub-stage values, field names,
decision values, link types, which fields are platform-written, how board users match accounts,
the polling interval) lives in `adlc-specs/tracker_mapping.yaml`. It is validated with the other
terminal specs, and checked against the board's process before the sync starts.

**Why this priority**: constitution II and VII: no tracker value in platform code, and a wrong
mapping must fail at start, not halfway through a decision.

**Independent Test**: remove a terminal's column from the mapping; spec validation fails naming
the terminal. Map a decision value to a field the board does not have; the mapping check against
the simulator fails naming the field, and the sync does not start.

**Acceptance Scenarios**:

1. **Given** the mapping, **When** the specs are validated, **Then** it is checked against its
   schema and against the terminal specs: every terminal has a column, every run state has a
   sub-stage, every human outcome and waiver or escalation action in any terminal's decision form
   has a decision value, every decision input has a field.
2. **Given** the mapping and a reachable board, **When** the mapping check runs (at sync start, or
   on demand), **Then** every mapped item type, state, field and link type exists in the board's
   process, and the service account can authenticate; any gap is reported by name and the sync
   does not start.
3. **Given** platform code, **When** it is scanned, **Then** it holds no tracker-specific value (item
   type, state, field or link name); those come only from the mapping.

---

### User Story 9 – Sync health and resilience (Priority: P3)

The CoE lead can see whether the sync is healthy: how far behind outbound delivery is, how old the
inbound watermark is, how many board changes were refused and reverted, and the drift found by the
last reconciliation. The sync survives restarts and board outages without losing or repeating a
change.

**Why this priority**: the operations console (019) shows these; this feature records them and
makes them available.

**Independent Test**: stop the board for longer than one polling interval while people change
items, then start it; every change made while it was down is processed once after it returns, and
the health data shows the watermark age rising then falling.

**Acceptance Scenarios**:

1. **Given** the sync running, **When** the health data is read, **Then** it shows outbound
   pending count and oldest pending age, inbound watermark and its age, last successful poll,
   refused and reverted counts by reason, and the last reconciliation's time and drift count.
2. **Given** the platform restarted between two polls, **When** it starts, **Then** inbound sync
   resumes from the stored watermark and misses and repeats nothing.
3. **Given** the board refuses a write as a conflict (someone changed the item since the platform
   read it), **When** the projector retries, **Then** it re-reads the item and writes again without
   overwriting a person's unread change.

---

### User Story 10 – One contract suite for every adapter (Priority: P3)

A suite of tests describes what any board adapter must do (create, read, update with a revision
check, link, comment, read changes since a watermark, find users), and the ADO adapter passes it
against the simulator, started from this repository in CI, reusing the simulator's published
fixtures.

**Why this priority**: it is how a real ADO organisation, or another tracker, is checked later
without changing platform code.

**Independent Test**: run the contract suite against the simulator; every case passes; point it at
a simulator with a deliberately changed response; the suite fails naming the case.

**Acceptance Scenarios**:

1. **Given** the suite and a running simulator, **When** it runs, **Then** every adapter operation
   the engagement layer uses is exercised, including refusals (stale revision, unknown item, no
   token).
2. **Given** the platform's code, **When** the boundary test runs, **Then** it imports nothing from
   the simulator's code (and the simulator nothing from the platform's).

---

### Edge Cases

- A person sets the decision field and edits the comment in two separate saves: the decision is
  read with the comment as it stands in the decision's revision; a comment saved later does not
  re-decide.
- Two people save decisions on the same run item between two polls: both revisions are read in
  order and processed in order; the second is judged against the run as the first left it.
- A person's change and the platform's projection of a different change race: the platform writes
  with a revision check; on conflict it re-reads and merges, never discarding the person's change
  unread.
- An item is deleted or moved to "Removed" on the board: a linked item is recreated by
  reconciliation; no platform state changes.
- The board's clock and the platform's differ: the watermark comes only from the board's own
  answers (`asOf`), never from the platform's clock.
- A use case is terminated in the platform: its Epic and its items move to the mapped "terminated"
  state (Removed in the demo mapping; a completed use case goes to Closed); later changes on them are refused as "use case closed".
- A decision value the mapping does not know (typed by hand): refused and reverted with the list of
  allowed values.
- A comment line that looks like an input but names no known input (`root-cause: x`): it stays part
  of the comment text and is not read as an input; if the decision needed that input, it is refused
  naming the input and its accepted forms.
- The service account's token is wrong or revoked: the sync stops, health shows "board
  authentication failed", the platform keeps working, and the inbox keeps working.
- Very long comments or answers: bounded by the board's limits (1 MB); the platform's own limits
  (comment 4,000 characters, reason 2,000) apply and a longer value is refused with the limit.

## Requirements *(mandatory)*

### Functional Requirements

**Port, adapter and mapping**

- **FR-001**: The platform MUST reach a tracker only through a board-neutral interface
  (`BoardAdapter`) and board-neutral types (item, link, comment, change, identity); the ADO adapter
  implements it for the ADO REST API 7.1 and is the only code that knows ADO's shapes.
- **FR-002**: The ADO adapter MUST take the board's base URL, the identities base URL, the
  organisation, the project and the service account's token from settings; the token is a secret
  and never logged or stored outside the settings.
- **FR-003**: Every tracker-specific name and value (item types, states and columns, sub-stage
  values, field references, decision values, link types, area path, platform-written fields, the
  identity matching rule, polling interval) MUST come from `adlc-specs/tracker_mapping.yaml`; no
  such value appears in platform code (checked by a scan).
- **FR-004**: The mapping MUST be validated with the terminal specs (schema, and completeness
  against every terminal: column, run-state sub-stages, decision values for every human outcome,
  waiver and escalation action, fields for every decision input) and checked against the board's
  process before inbound or outbound sync starts; a failed check names each gap and stops the sync
  without affecting the rest of the platform.

**Outbound projection**

- **FR-005**: Each use case MUST have one Epic; each terminal run one run item under it; each
  clarification round one clarification item under its run item (so in its Epic's tree). Each is created when the
  platform first records the use case, run or round.
- **FR-006**: The Epic's column MUST be its current terminal's column (or the closed column) and its
  sub-stage the current run's state; the run item's state, decision values offered, required
  inputs, reviewer recommendation and evidence link MUST match the run. Only the service account
  writes them.
- **FR-007**: Projection MUST be delivered after the platform's transaction commits, in order per use
  case, with the outbox's retry schedule and dead-letter rule (dead letters visible to the CoE and
  requeued by them); a board outage never blocks or fails a platform operation. (Changed at Gate 2,
  plan research R-03: the outbox itself delivers inside a write transaction, so the board keeps its
  own delivery state.)
- **FR-008**: Every write MUST use the board's revision check; on conflict the projector re-reads,
  re-applies only platform-written fields, and retries.
- **FR-009**: Decisions, waivers, clarification answers and escalation completions made in the inbox
  MUST be projected the same way as those made on the board.

**Inbound sync**

- **FR-010**: Inbound sync MUST poll the board every mapped interval (default 10 seconds) for items
  changed at or after the previous answer's `asOf`, read each returned item's updates, and process
  each update not yet processed, in update order per item and items in the order the board returns
  them; it MUST NOT lose an intermediate change between two polls. The watermark advances only
  after every item of a poll was processed; a failure leaves it where it was, and the next poll
  re-reads (already processed updates are skipped by FR-012).
- **FR-010a**: On its first start against a board (no stored watermark), inbound sync MUST NOT
  replay the board's existing history: it starts from the board's latest change at that moment
  (or from `ADLC_BOARD_START_FROM` when set), and reconciliation brings older items in line with
  the platform.
- **FR-011**: Updates made by the platform's service account MUST be skipped.
- **FR-012**: Each processed update MUST be recorded with its work item id and update number before
  its effect is applied, so the same update is never turned into a second command (idempotency
  across overlaps and restarts). The update number, not the revision, identifies a change: an
  update recording the other side of a link keeps the item's revision (015 T001).
- **FR-013**: Before any decision right is checked, the changer MUST be mapped to a platform account
  through the identity rule (board identity ↔ account in the accounts file; roles from the
  account and `roles.yaml`); an unmapped changer's request is refused.
- **FR-014**: Inbound changes MUST become the platform commands the inbox uses today, with the same
  checks and the same records: register use case (emits `usecase.submitted`), answer clarification,
  sign-off decision (`pass`, `rework`, `exception`, `terminate`), waiver decision (approve or
  reject), escalation completion (without artifact changes). No platform rule is re-implemented in
  the engagement layer.
- **FR-015**: A decision MUST be read from the decision field together with the comment and decision
  inputs as they stand in the same revision; a decision that needs a comment, root cause, reason,
  rework target or emitted value is refused without it.
- **FR-016**: Every board change is a request. A refused request (decision rights, missing input,
  stale run, unknown value, unmapped user, already answered) MUST be reverted on the board by the
  service account with a comment giving the platform's reason; an accepted request is followed by
  the projection of its result and the decision field is cleared for the next decision.
- **FR-017**: A person's change to a platform-written field (column, sub-stage, platform ids, offered
  values, evidence link) MUST be reverted with a comment; changes to fields the mapping does not
  read MUST be ignored.
- **FR-018**: A new Epic in the mapped area, created by a mapped person and not linked to a use case,
  MUST be registered as a use case with its title as name and description as intake text; an Epic
  that cannot be registered gets a comment with the reason and is re-read when changed.

**Reconciliation**

- **FR-019**: A person with the CoE role (the role named by `ADLC_DEADLETTER_ROLE`) MUST be able to
  start reconciliation and requeue dead-lettered projections from the command line
  and through the platform API; it is never started on a schedule in this feature.
- **FR-020**: Reconciliation MUST compare every use case, run and clarification round with its board
  item, correct platform-written fields that differ, create missing items and links, and return a
  report of each difference (item, field, board value, platform value, action); it MUST NOT change
  platform state.

**Data, health and observability**

- **FR-021**: The platform MUST store the link between each platform object and its work item (id and
  last revision written), the inbound watermark and delivery state, and one record per processed
  inbound revision with its outcome (command, refused with reason, ignored), in new migrations of
  its own database; these records are append-only where they are history.
- **FR-022**: The platform MUST make sync health available (outbound pending count and oldest age,
  watermark and its age, last poll, refused and reverted counts by reason, last reconciliation time
  and drift) for the operations console (019); this feature exposes it through the API and the
  command line.
- **FR-023**: Every inbound command and outbound write MUST be traced and logged with the use case,
  run, work item and revision, never with field values, comments, answers or tokens.
- **FR-024**: Every command applied from the board MUST be recorded in the run's activity and, where
  the inbox would, in the decision log and ledger, attributed to the mapped person, with the board
  work item and revision as its source.

**Contract and boundaries**

- **FR-025**: A contract suite MUST describe every adapter operation the engagement layer uses; the
  ADO adapter MUST pass it against the simulator started from this repository, reusing the
  simulator's published fixtures, in the platform's checks.
- **FR-026**: The platform MUST import nothing from the simulator's code, and the simulator nothing
  from the platform's (boundary tests).
- **FR-027**: The inbox MUST keep working unchanged; decisions can be made in either place, and the
  two never disagree once a poll and the outbox have caught up.
- **FR-028**: The inputs a decision needs beyond its value and comment (root cause, reason, rework
  target terminal, values a pass emits) MUST be accepted in three ways, in this order:
  1. **Dedicated board fields**, one per input (Root Cause, Reason, Rework Target, and Values with
     one `name: value` per line), named in the mapping and added to the simulator's seed.
  2. **The decision comment**, for an input whose field is empty: one line per input in the fixed
     form `<input>: <value>` (the input names come from the mapping), the rest of the comment being
     the comment itself. When a field and a comment line both give an input and differ, the field
     wins and the comment line is ignored, which the platform states in its reply comment.
  3. **The platform's console** (the inbox today), which stays available for every decision
     (FR-027).
  A value that cannot be read (an unknown root cause, an unknown terminal, a malformed line, a value
  of the wrong type) is refused naming the input and the allowed values.

### Key Entities

- **Board item**: the board-neutral view of a work item: id, revision, type, state, fields,
  links, the identity that last changed it.
- **Board change**: one revision of one item read by inbound sync: item id, revision, changer,
  changed fields (old and new values), link changes, time.
- **Tracker mapping**: the declarative description of how platform objects and decisions appear on
  the board (types, columns, sub-stages, fields, decision values, links, platform-written fields,
  identity rule, area, polling interval).
- **Board link**: platform object (use case, run, clarification round) ↔ work item id and the last
  revision the platform wrote.
- **Sync state**: inbound watermark (the board's `asOf`), last poll time and outcome, outbound
  delivery position.
- **Inbound command record**: work item id, update number and revision, changer, mapped account, the command it
  became (or "ignored"), outcome (accepted or refused with reason), revert written.
- **Reconciliation report**: start and end time, who started it, each difference and the action
  taken.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A decision saved on the board takes effect in the platform, and its result shows on
  the board, within 30 seconds at the default polling interval, in 95% of cases on the demo host.
- **SC-002**: A platform state change shows on the board within 15 seconds in 95% of cases while the
  board is reachable.
- **SC-003**: In a test of 500 board changes by several people across 20 use cases, including
  overlapping polls and a restart in the middle, every change is processed exactly once, in order
  per item, and the platform's records match the inbox-equivalent decisions one for one.
- **SC-004**: 100% of refused board changes (a scripted set covering every refusal reason) are
  reverted with a comment naming the reason, and none changes platform state.
- **SC-005**: After a board outage of 10 minutes with changes on both sides, all pending outbound
  updates and inbound changes are delivered after it returns, with none lost or duplicated.
- **SC-006**: Reconciliation of 50 use cases with 10 injected differences reports and corrects all
  10, and a second run reports none, in under 1 minute.
- **SC-007**: The full lifecycle of one use case (D-1 to D-9's decisions: sign-offs, rework,
  exception and waiver, clarification, escalation, termination) can be driven entirely from the
  board's API, with the ledger identical in kind to an inbox-driven run (same records, attributed
  to the same people).
- **SC-008**: The adapter contract suite passes against the simulator in every platform check run,
  and the platform code scan finds no tracker-specific value.

## Assumptions

- The simulator's seed gains the decision-input fields (Root Cause, Reason, Rework Target, Values);
  these are data changes to `ado_sim/seed/demo.yaml`, and the 015 contract fixtures are regenerated
  only if a fixture's expected body changes.
- The board is the feature 015 simulator, reached over HTTP on the platform network (compose) or on
  localhost (`make local`); the simulator's seed is changed only by adding what the mapping needs
  (data, not code).
- The platform trusts the board's attribution of each change (who changed it), as it trusts its own
  session sign-in: the board authenticates its users. A board administrator who can act as another
  user could therefore act for them; for Option A the board is the local simulator run by the
  platform's operators, and for a real ADO organisation the same trust is placed in its
  administrators (to be confirmed before a real tracker is connected).
- The service account is the seeded `adlc-platform@adlc.demo`; its token is issued with the
  simulator's command and placed in the platform's settings.
- Each account in the accounts file can name its board identity (the board's unique name); the
  identity rule in the mapping says which account property to match. Accounts without one cannot
  act on the board.
- Polling every 10 seconds is enough for the demo; the interval is a mapping setting.
- Escalation completion from the board keeps the run's current artifacts; editing artifacts stays
  in the platform's console (SA §22.4 evidence viewer).
- Change requests and proposed operational events (feature 012) and supplying evidence for a
  blocked run stay in the inbox (later the console); they are not board actions in Option A.
- One person's save is one request: when a run needs several approvers, each saves the decision
  separately; after each accepted approval the platform clears the field so the next approver can
  save the same value again.
- Clarification rounds with several questions are answered in one save, one numbered answer per
  question.
- Existing use cases (from before this feature) reach the board through the first reconciliation;
  there is no separate backfill.
- Concurrency control on the platform side is unchanged: each command uses the run's version as the
  inbox does; the board's revision check guards the board side.
