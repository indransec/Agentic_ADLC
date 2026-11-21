# Feature Specification: End-to-End Demo on the Board

**Feature Branch**: `020-e2e-demo-on-board`

**Created**: 2026-11-21

**Status**: Draft

**Input**: User description: "020 e2e-demo-on-board — Phase 2 Option A (SA §22.9, §22.10, build
plan §11). The SA §21 demo (feature 014) driven from the board: D-1 to D-9, plus D-12 (a board
change without the right is reverted with the reason) and D-13 (the board is changed out of step
and reconciliation corrects it); the agents' replies re-recorded if the board flow needs it; a
rehearsal on the full stack."

## Clarifications

### Decided before this feature (recorded for context)

- Feature 014 built the demo: `demo/script.yaml` (15 steps over two use cases: the Incident
  Triage reference for D-1 to D-3 and D-5 to D-9, a second one for D-4), the driver
  (`adlc-demo`: presenter mode waits for people, `--auto` acts as them, `--live` uses real
  models), rehearsed agent replies (`demo/recordings`, `demo/rehearsed`), `make demo*`, the pilot
  faults through the operator tool, and the report of every step and moment.
- 015–019 built the board (the ADO simulator's API and pages), the sync, and the console: with the
  sync on, people decide on the board and the web app is the operations console (019).
- SA §22.10: Option A shows D-1 to D-9, D-12 and D-13 on the board; D-10, D-11 and D-14 arrive
  with Option B. The inbox stays available until this feature passes.
- Agents are unchanged by Option A; the replies are matched in call order per agent, not by
  prompt text.

### Session 2026-11-21

- Q: Where is the release's change request approved when the board drives decisions? → A: on the
  board: a fourth item kind (the change request, an item under its run's item), decided with
  Approve change or Reject change in the decision field.

## User Scenarios & Testing *(mandatory)*

The actors are the presenter (who plays each role on the board), the CoE (who operates the sync
from the console), the audience, and the demo driver.

### User Story 1 – The demo, decided on the board (Priority: P1)

The presenter runs the demo with the board sync on. At each human step the driver says what to do
on the board, as which demo user, on which item (the Epic, the run item, the clarification item)
and with which values; the presenter does it on the board's pages; the driver sees the platform
move and goes on. The journey and KPIs (D-8) are shown in the console.

**Why this priority**: it is the point of Option A: the demo's decisions are made where people
work, the board.

**Independent Test**: `make demo-auto` with the board on runs every step with the driver acting
on the board as each person (never through the platform's services), and the report shows every
expected outcome and D-1 to D-9 with the runs that prove them.

**Acceptance Scenarios**:

1. **Given** the board sync on, **When** a step submits a use case, **Then** it is an Epic created on
   the board by the business owner, registered by the sync (not a platform call).
2. **Given** a pass, rework, exception, waiver decision or escalation completion, **When** the step
   runs, **Then** it is the decision field (with its comment and inputs) saved on the run item by
   the named demo user, and the platform's answer arrives on the item.
3. **Given** a clarification, **When** the step answers it, **Then** the answer is saved on the
   clarification item by the addressed demo user.
4. **Given** presenter mode, **When** a human step comes, **Then** the driver prints the item's board
   address, the demo user, the decision value and every input to type, and waits until the
   platform shows it.
5. **Given** the step's expectation, **When** the platform moves, **Then** the driver checks it as in
   014 (state, final status, run number, arrow, escalation) and reports it.

---

### User Story 2 – The release's change approval (Priority: P1)

At T6 the release needs its ITSM change request approved by the release manager (step 10). On the
board a change request is a fourth item kind: an item under its run's item, showing the change
(its summary, risk and window, and what waits for it), decided with Approve change or Reject
change in the decision field, with a comment. The sync applies it as the inbox does (feature 012's
change decision, the decision rights of the ITSM server's owner role), answers with a comment and
keeps the item's state in step (awaiting a decision, approved, rejected).

**Why this priority**: without it the demo stops at T6 (D-5, D-6).

**Independent Test**: step 10 completes with the board on: the change request item appears under
the T6 run item, the release manager approves it on the board, the run's controls re-run and the
run passes.

**Acceptance Scenarios**:

1. **Given** an agent raises a change request for a run, **When** the sync projects, **Then** an item
   of the mapped type appears under the run's item with the change's summary and state.
2. **Given** the release manager, **When** they set Approve change (or Reject change) with a comment,
   **Then** the platform records the decision as theirs (as the inbox's change decision does), the
   item shows the new state and the waiting run's controls re-run.
3. **Given** a person without the ITSM owner role, **When** they decide the change, **Then** it is
   refused with a comment and cleared (as D-12).
4. **Given** a change already decided, **When** someone sets a decision again, **Then** it is refused
   with a comment.

---

### User Story 3 – D-12: a change without the right is reverted (Priority: P2)

A demo step has a person change something on the board they have no right to (a column the
platform owns, or a decision on a run they may not sign off); the platform sets it back and says
why in a comment.

**Why this priority**: it shows that the board is an interface, not the authority (SA §22.1).

**Independent Test**: the step runs; the item is back as it was and carries the platform's comment
naming the reason; the report shows D-12 with the item.

**Acceptance Scenarios**:

1. **Given** the step, **When** a person sets an Epic's state on its form, **Then** it is set back
   with a comment within the sync's poll interval.
2. **Given** the step, **When** a person without the right decides a run, **Then** the decision is
   refused with a comment and cleared.

---

### User Story 4 – D-13: drift corrected by reconciliation (Priority: P2)

The board is put out of step with the platform (a platform-written field changed in a way the sync
does not see as a person's change); the CoE opens Sync status in the console, runs "Reconcile now",
and the board is corrected; the differences are listed.

**Why this priority**: it shows the platform stays the source of truth even when the board drifts
(016 FR-025).

**Independent Test**: the step runs; the reconciliation lists the drifted field and the board shows
the platform's value again; the report shows D-13 with the reconciliation.

---

### User Story 5 – Rehearsal and readiness (Priority: P2)

Before an audience, the presenter rehearses on the full stack: reset (platform, pilot and the
board), the board's demo users given page passwords, the sync on, the demo run with `--auto`, the
report checked; the presenter guide says what to show on the board and in the console at each step
and how to recover (resume from a step, fall back to the inbox).

**Why this priority**: the MVP gate is "MVP demo accepted" (SA §19).

**Independent Test**: `make demo-reset` then `make demo-auto` on the demo environment passes every
step twice in a row; the guide's recovery steps are walked once.

**Acceptance Scenarios**:

1. **Given** `make demo-reset`, **When** it runs, **Then** the board is reset too (its data, seeded
   again, the demo users' page passwords set, the service account's token issued and given to the
   sync), and it is refused outside `ADLC_ENV=demo` as before.
2. **Given** a stop mid-demo, **When** the presenter resumes from a step, **Then** the driver finds
   the use cases and their board items and goes on.
3. **Given** the board down during the demo, **When** the presenter falls back, **Then** the guide
   says how (turn the sync off: the inbox returns, 019) and the driver continues in inbox mode.

---

### Edge Cases

- A step's item is not on the board yet when the driver reaches it (the sync's poll interval): the
  driver waits for it, then acts.
- The presenter makes the wrong decision on the board: the platform refuses or records it; the
  driver reports the step's expectation as failed and says how to resume.
- The recorded replies no longer replay (the board flow changed an agent's input or call order):
  the replies are re-recorded and the recordings' provenance updated.
- The board is slow (polling): every step allows the sync's poll interval plus the platform's
  processing before it is judged.

## Requirements *(mandatory)*

### Functional Requirements

**Driving the demo from the board**

- **FR-001**: The demo driver MUST be able to act on the board as each demo person (the board
  users mapped to the platform's accounts), creating Epics, saving decision fields with their
  comment and inputs, and answering clarification items, never calling the platform's services for
  a human step, when the board sync is on.
- **FR-002**: In presenter mode the driver MUST tell the presenter, for each human step, the board
  item's address, the demo user to act as, and every value to choose or type; and wait until the
  platform shows the step done.
- **FR-003**: The driver MUST find a step's board items through the platform (016's links), waiting
  for the sync to project them.
- **FR-004**: With the board sync off, the driver MUST behave as feature 014 built it (the inbox).
- **FR-005**: The script MUST stay data: the steps name roles, decisions and inputs; the board's
  field names and values come from the tracker mapping, never from the script or the driver's code.

**New moments**

- **FR-006**: The script MUST have a step for D-12 (a person's change without the right, reverted
  with a comment; after the main journey's T1) and one for D-13 (board drift corrected by
  reconciliation from the console; before T9), with expectations the driver checks. Neither step
  touches an agent, so the recorded replies' call order is unchanged. The drift is a demo device
  (a platform-written field changed with the service account's token, which the sync reads as its
  own), not a supported operation; the guide says so.
- **FR-007**: The report MUST list D-1 to D-9, D-12 and D-13 with the runs, items or
  reconciliation that show each.

**The change approval**

- **FR-008**: Change requests MUST be a board item kind in the tracker mapping (data: the item type,
  its fields, its states, and the decision values Approve change and Reject change), projected
  under their run's item and kept in step by the sync and by reconciliation. Every change request
  of a run has an item, decided or not (its state shows the decision).
- **FR-008a**: A change decision on the board MUST be applied through the platform's existing change
  decision (feature 012: rights, append-only record, the waiting runs' controls re-run), with the
  refusal comments and reverts of 016; the mapping check (016 V-32 to V-36) MUST cover the new kind,
  and the simulator's seed MUST offer the new decision values (kept in step by 018's contract test).

**Rehearsal**

- **FR-009**: `make demo-reset` MUST reset the board with the platform (simulator data reseeded,
  page passwords for the demo users, the service account's token for the sync, the people's
  tokens for the driver) and stay refused outside the demo environment. Tokens are registered with
  a simulator-only import (never replacing a registered token, refused for an unknown user;
  recorded as a difference from ADO), read from `.env` and a demo file outside the repository
  (mode 600), never printed or committed.
- **FR-010**: The presenter guide (`demo/README.md`) MUST describe the board flow: what to open
  on the board and in the console at each step, the demo users, and the recovery paths (resume,
  fall back to the inbox).
- **FR-011**: The recorded replies MUST replay under the board flow; if they do not, they MUST be
  re-recorded with their provenance.

### Key Entities

- **Board action** (script data): a human step on the board: the demo role, the item (use case,
  run, clarification, change), the decision value or answer, and the inputs.
- **Change request item** (board): the fourth kind (016 had use case, run, clarification): an item
  under the run's item, its state awaiting a decision, approved or rejected.
- **Demo report** (014): extended with the board items and D-12, D-13.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `make demo-auto` with the board on passes every step, twice in a row, from a reset.
- **SC-002**: Every human step of the auto run is a board change by the named demo user (100%,
  checked in the simulator's history and the platform's run activity with source "board").
- **SC-003**: The report shows D-1 to D-9, D-12 and D-13, each with at least one run, item or
  reconciliation.
- **SC-004**: Each board step is acted on by the platform within one poll interval plus the
  platform's processing (about 15 s in the demo settings), so the whole auto run takes at most the
  014 run's time plus 15 s per human step.
- **SC-005**: A presenter who has not seen the board flow can run the demo from the guide alone at
  the rehearsal (observed once, with notes).

## Assumptions

- The demo users are the simulator's seeded users, mapped to the demo accounts by
  `board_identity`; the driver acts as them with their personal access tokens (issued at reset) or
  their page sessions (decided in the plan).
- The fault steps (the pilot's model swap) are unchanged.
- The rehearsal runs on the demo environment with Docker; the layout check at 1280×720 is part of
  it.
