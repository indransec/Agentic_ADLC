# Feature Specification: Human Inbox

**Feature Branch**: `007-human-inbox`

**Created**: 2026-11-11

**Status**: Draft

**Input**: User description: "Feature 007 human-inbox (build plan §6 row 007; SA §8 human-in-the-loop
and experience layer): session-protected platform operations for intake, inbox, run detail,
sign-off, clarifications, waivers, escalations, artifact editing, attachments, use-case journey and
ledger verification, and one web application (intake form, inbox, run detail with sign-off,
artifact editor, clarification, waiver and escalation forms, journey view) that uses only those
operations."

## Clarifications

### Session 2026-11-11

- Q: Should feature 007 send email notifications, or only show them in the in-app inbox? → A:
  In-app only. Email comes later on the same notification point. No mail server or account email
  addresses are needed now.
- Q: Who may read a use case's journey, run details, artifacts and evidence? → A: Any signed-in
  person. Actions stay limited by role. This matches feature 005's views; restriction by data
  class comes later.

### Change request 2026-11-11 (live walkthrough)

- Q: A submitted use case was blocked by T0's prerequisite (intake under 200 characters), and
  nothing told the business owner why or where to act. Should blocked runs be surfaced? → A: Yes.
  A blocked run appears in the inbox of its terminal's accountable roles, and the run detail
  shows each prerequisite with its result and reason, so the owner can supply the evidence or
  terminate the run.

## User Scenarios & Testing *(mandatory)*

Agents build, humans decide (constitution III). Until now people could act on the platform only
through test harnesses and a demo script. This feature gives them one web application where they:

- submit use cases;
- see what is waiting for them;
- act on it with full context.

Every action goes through the same service operations the orchestrator and ledger already
provide. Each action is therefore authorized by role, logged, and recorded in the ledger
(constitution IV, V). People never edit specs or ledger records directly (SA §8).

### User Story 1 - A business owner submits a use case and follows it (Priority: P1)

A business owner:

1. signs in;
2. fills in the intake form (a name and a free-text description);
3. submits it.

T0 opens for the new use case. The business owner then sees the use case in **My use cases**
and can open its journey: every terminal run so far, with its state, outcome, time in automatic
steps, time waiting for people, and cost.

**Why this priority**: it is the entry point of the lifecycle (SA §8.1 "Submit use case").
Without it nothing else in the application has data.

**Independent Test**: sign in as a business owner, submit a use case, and see T0 opened in the
journey within one orchestrator round.

**Acceptance Scenarios**:

1. **Given** a signed-in business owner, **When** they submit a name and description, **Then**
   the use case is created and T0 opens. The use case is listed under **My use cases**.
2. **Given** a person without the accountable role of the terminals a submission opens, **When**
   they submit, **Then** the request is refused with the reason.
3. **Given** a use case with closed and open runs, **When** its journey is opened, **Then** it
   lists each run with:
   - terminal, state and final status;
   - time in automatic steps and time waiting for people;
   - cost.

---

### User Story 2 - An approver signs off from the inbox with full context (Priority: P1)

An approver's **inbox** lists the runs waiting for their sign-off: those in which they hold a
role of the run's sign-off rule, including a required conditional approver. A run they have
already approved does not appear.

Opening a run shows the **run detail**. Per SA §8.2, this always includes:

- the artifacts, with their current version, producer and attachments;
- the automated control results, with reasons;
- the reviewer's recommendation: status, reason, root cause, a score per checklist item, and
  findings;
- prior rework comments for this terminal;
- the timer state (due time, overdue or not).

The approver then decides:

- **pass**;
- **rework**, with a comment and a root cause;
- **exception**, with the waiver fields the spec asks for;
- **terminate**, with a comment.

A decision that differs from the reviewer's recommendation needs a short reason (SA §8.2).

**Why this priority**: sign-off is the human decision the whole lifecycle waits on.

**Independent Test**: as the T1 product owner, open T1 from the inbox. Check that every item of
SA §8.2 is shown. Pass it against a reviewer's rework: refused without a reason, accepted with
one.

**Acceptance Scenarios**:

1. **Given** T1 awaiting sign-off, **Then** it appears in the inbox of each person holding one
   of T1's sign-off roles, and in no one else's inbox.
2. **Given** the reviewer recommended rework, **When** the approver passes without a reason,
   **Then** the decision is refused with the reason. With a reason, it is recorded.
3. **Given** a rework decision without a comment or a root cause, **Then** it is refused. With
   both, the run closes as rework and the next run opens as the outcome model routes it.
4. **Given** an exception decision, **Then** the form asks for exactly the fields the spec
   requires (for example risk acceptance, expiry, compensating control, waiver owner), and a
   pending waiver is created.
5. **Given** the run changed after the approver opened it, **When** they decide, **Then** the
   decision is refused as stale. The approver reloads and decides again.
6. **Given** a rule that needs two approvers, **When** the first approves, **Then** the run stays
   in the second approver's inbox, and the detail shows who has approved.

---

### User Story 3 - Approvers edit artifacts before approving (Priority: P1)

On the run detail, a person holding a sign-off or accountable role of the terminal can:

- edit an artifact table in place;
- upload a spreadsheet for a table artifact;
- attach a file to an artifact.

Each change creates a person-produced version (feature 005). It clears earlier approvals,
withdraws a pending waiver, and the controls are re-run. The detail shows the version history.
Attachments are offered as downloads only, never displayed in the page.

**Why this priority**: SA §8.1 "Edit an artifact before approving" is what makes an approval
mean the approver stands behind the content. It drives the human-edit-rate KPI.

**Independent Test**: edit one cell of T1's KPI table, then check that:

- a version produced by a person exists;
- earlier approvals no longer count;
- the controls re-ran.

Then upload a spreadsheet and attach a note, and download the attachment.

**Acceptance Scenarios**:

1. **Given** an edited table, **When** saved, **Then** a new version records the person. The
   inbox and detail show "controls being re-run" until the re-check finishes. Then the new
   control results are shown.
2. **Given** an unchanged table, **When** saved, **Then** no version is created and the person is
   told so.
3. **Given** a spreadsheet that does not fit the artifact's columns, **Then** the upload is
   refused with the reason. A fitting one replaces the rows and is kept as an attachment.
4. **Given** a file of a type not on the allow list or over the size limit, **Then** it is refused
   with the reason. An accepted file can be downloaded, and it is never rendered inline.
5. **Given** a person without a sign-off or accountable role, **Then** the artifact editor is
   read-only for them, and the operation is refused if called directly.

---

### User Story 4 - Clarifications, escalations and waivers reach the right person (Priority: P2)

The inbox also lists, for the signed-in person:

- clarifications addressed to a role they hold;
- escalated runs of terminals where they hold the accountable role;
- pending waivers they may decide, where they hold an approver role and are not the proposer;
- for the CoE role only: dead-lettered events.

Each item opens a form:

- **Clarification:** answer the agent's or reviewer's questions; the same run resumes.
- **Escalation:** complete the artifacts by hand; the run then goes to normal sign-off.
- **Waiver:** approve or reject, with a comment.
- **Dead letter:** requeue the event.

**Why this priority**: these keep runs from stalling. They are less frequent than sign-off.

**Independent Test**: script a clarification at T2. Answer it as the addressed role and see the
same run resume. Escalate a run and complete it as its accountable owner. Approve a waiver as a
different person than the proposer.

**Acceptance Scenarios**:

1. **Given** a clarification addressed to the engineering lead, **Then** only people with that
   role see it. Their answer resumes the same run and does not count as rework.
2. **Given** an escalated run, **When** its accountable owner completes the artifacts, **Then** the
   run reaches sign-off. Anyone else is refused.
3. **Given** a pending waiver, **When** the proposer tries to approve it, **Then** it is refused.
   Another approver's decision is recorded with their comment.
4. **Given** a dead-lettered event, **Then** only the CoE role sees it and can requeue it.

---

### User Story 5 - Evidence can be checked from the application (Priority: P2)

Any signed-in person can:

- see a run's activity timeline;
- see its version history;
- see its ledger record reference;
- start a ledger verification for a use case and see the result: verified, or the breaks with
  record and element.

**Why this priority**: verification exists (feature 005), and auditors should not need a command
line to use it.

**Independent Test**: verify a use case from the application and see "verified" with the number of
records checked.

**Acceptance Scenarios**:

1. **Given** a use case, **When** a signed-in person verifies it, **Then** the result appears and
   the verification run is recorded under their account.
2. **Given** a run, **Then** its timeline lists every step with actor type, start, end and
   duration.

---

### Edge Cases

**Concurrency**

- Two approvers decide at the same moment on a two-approver rule: both decisions count, and the
  run closes once.
- The run moved on (closed, or rework opened a new run) while a person was looking at it. Their
  decision is refused as stale or invalid, with a message to reload.

**Sessions**

- A session expires while a form is open. The action is refused as not signed in; the person
  signs in again and resubmits.

**Inbox edge cases**

- A person holds several roles: the inbox lists each item once, with the role that makes it
  theirs.
- A run waiting for a required conditional approver (`plus`) appears for that role even if its
  base rule is already satisfied.

**Uploads and display**

- A large artifact table is editable up to 1,000 rows, with scrolling, and saving keeps the whole
  table as one version. Above 1,000 rows the table is read-only, and spreadsheet upload is
  offered instead.
- An attachment with an allowed type but a dangerous name (path characters) is refused or renamed
  safely (feature 005 rule).
- Text from agents or people (artifacts, comments, findings) is shown as text, never interpreted
  as markup or script.

## Requirements *(mandatory)*

### Functional Requirements

**Access**

- **FR-001**: Every platform operation of this feature MUST require a signed-in session. Only
  the existing public paths (health and sign-in) stay open.
- **FR-002**: Every operation MUST act as the signed-in person, with their roles from the account
  file and role catalogue. The application MUST NOT let a person act as another person or role.
- **FR-003**: Authorization MUST be the existing service rules: sign-off roles, accountable roles,
  addressed roles, waiver approvers, the CoE role. The application only hides actions a person
  cannot take. A refused direct call gives the service's reason.

**Use cases and journey**

- **FR-004**: A signed-in person MUST be able to submit a use case (name of 1–200 characters,
  description of 1–20,000 characters). The submitter must hold the accountable role of the
  terminals a submission opens (T0's business owner, read from the registered specs). This rule
  is added to feature 003's submit operation, so every channel enforces it.
- **FR-005**: **My use cases** MUST list the use cases the person submitted or holds a role in.
  The journey of a use case MUST list its runs with:
  - terminal, run number, state and final status;
  - opened and closed times;
  - time in automatic steps and time waiting for people (feature 005 summary);
  - cost (feature 006).

**Inbox**

- **FR-006**: The inbox MUST list, for the signed-in person:
  - runs awaiting their sign-off: they hold a role of the run's rule or a required conditional
    role, and have not approved yet;
  - clarifications addressed to a role they hold;
  - escalated runs where they hold the accountable role;
  - pending waivers they may decide (an approver role, not the proposer);
  - blocked runs where they hold the accountable role (change request 2026-11-11);
  - for the CoE role, dead-lettered events.

  Each item shows the use case, terminal, what is asked, when it arrived and its due time.
  Items are ordered soonest due first, then by arrival; items without a due time come last.
- **FR-007**: The inbox MUST reflect a change (a decision, a new run, an answer) within one
  refresh. The application refreshes the inbox at least every 30 seconds while it is open.

**Run detail and decisions**

- **FR-008**: The run detail MUST always show (SA §8.2):
  - the artifacts, with their current version, producer and attachments;
  - control results with reasons, and the synthetic marker where evidence was synthetic;
  - the reviewer's recommendation: status, reason, root cause, scores per checklist item with the
    item text, and findings;
  - prior rework comments: every earlier run of this terminal in this use case that closed as
    rework, newest first, with who, when, comment and root cause;
  - clarification history;
  - approvals given so far;
  - the timer state;
  - the run version, and whether controls are being re-run;
  - the prerequisites, each with its description, result and reason, so a blocked run shows why
    it is blocked (change request 2026-11-11).
- **FR-009**: The decision form MUST offer only the outcomes the terminal allows for people. Its
  required fields MUST come from the pinned spec:
  - comment and root cause for rework, root causes from the catalogue limited to the spec's;
  - waiver fields for exception;
  - typed emitted values where the spec requires them.
- **FR-010**: A decision whose outcome differs from the reviewer's recommendation MUST carry a
  reason, as feature 003 requires. The form MUST ask for it before sending.
- **FR-011**: Every decision and edit MUST carry the run version it was made on. A decision on an
  older version MUST be refused as stale, with a message to reload.

**Artifacts and files**

- **FR-012**: A person holding a sign-off or accountable role MUST be able to:
  - edit an artifact table;
  - upload a spreadsheet for a table artifact;
  - attach a file.

  These use feature 005's operations and rules (versions, approval reset, waiver withdrawal,
  control re-check, size and type limits). Everyone else sees artifacts read-only.
- **FR-013**: Attachments MUST be served as downloads only:
  - the stored media type;
  - a "download" disposition;
  - a header forbidding content sniffing.

  They are never rendered inline. Text from agents and people MUST be displayed as plain text,
  never as markup.
- **FR-014**: The artifact version history MUST be viewable per artifact: version, producer, time
  and schema validity.

**Clarifications, escalations, waivers, dead letters**

- **FR-015**: The clarification form MUST show the questions, who asked, and where they looked.
  An answer MUST resume the same run.
- **FR-016**: The escalation form MUST let the accountable owner complete the artifacts. It uses
  the same table editing as FR-012 and then hands the run to sign-off.
- **FR-017**: The waiver form MUST show the proposal (risk acceptance, expiry, compensating
  control, owner, proposer) and let an allowed approver approve or reject, with a comment.
- **FR-018**: The CoE role MUST be able to list and requeue dead-lettered events.

**Evidence**

- **FR-019**: Any signed-in person MUST be able to see:
  - a run's activity timeline;
  - checks per attempt;
  - artifact versions;
  - the ledger record reference.

  They can also verify a use case's ledger and see the report (feature 005).

**Interface boundary**

- **FR-020**: The web application MUST use only the platform operations of this feature. It never
  reads or writes the data store directly. Every operation is available without the web
  application, so later channels (Teams, ServiceNow) can use the same operations (SA §8).
- **FR-021**: Errors MUST be distinguishable by kind:
  - not signed in;
  - not allowed (with the reason);
  - not found;
  - stale (reload);
  - not allowed in the run's current state;
  - invalid input (with the field).
- **FR-022**: No terminal-specific values in the platform operations or the web application
  (constitution I). Forms are built from the pinned spec and catalogues.

**Observability**

- **FR-023**: Every operation MUST be traced with the person's account and the run or use case.
  Every human action writes its run activity and sign-off records through the existing services
  (SA §8.2).

### Key Entities

- **Inbox item**: kind (sign-off, clarification, escalation, waiver, dead letter), use case,
  terminal, run, the role that makes it the person's, what is asked, arrival time, due time.
- **Run detail**: the view of FR-008, assembled from features 003, 005 and 006.
- **Decision**: outcome, comment, root cause, reason, waiver fields, typed emitted values, the run
  version it was made on.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person can submit a use case and see T0 opened in its journey in under 1 minute
  from opening the intake form.
- **SC-002**: 100% of inbox items are visible to every person who may act on them and to no one
  else (checked across the sample lifecycle's roles).
- **SC-003**: Every item of SA §8.2 is present on the run detail of every terminal T0–T8 of the
  sample lifecycle.
- **SC-004**: 100% of stale decisions (made on an older run version) are refused, and none is
  recorded.
- **SC-005**: Every human action taken through the application leaves its run activity record,
  and its sign-off record where one applies. The ledger of a use case driven entirely through the
  application verifies.
- **SC-006**: No platform operation except health and sign-in answers without a session.
- **SC-007**: An approver can go from the inbox to a recorded decision in under 2 minutes for a
  typical run, with all context on one screen.
- **SC-008**: The 003, 004, 005 and 006 suites still pass. The full sample lifecycle can be driven
  end to end through the platform operations alone.

## Assumptions

- **Web application:** the build plan names the stack (Streamlit, Apache-2.0, including its table
  data editor). Feature 013 later adds the KPI dashboard to the same application.
- **Sign-in:** local accounts and sessions from feature 001 are reused. Single sign-on comes
  later behind the same identity interface.
- **Out of scope:**
  - T7 rollout-stage approvals arrive with the deployment features.
  - Teams and ServiceNow approvals come later, on the same operations.
- **Visibility:** any signed-in person may read any use case's journey, run detail and evidence
  (clarified), as feature 005 decided for its views. Actions are limited by role. MVP data is
  synthetic.
- **Notifications:** an in-app inbox only in this feature (clarified). Email, Teams and
  ServiceNow come later on the same inbox and operations. SA §8.2's email for the MVP is
  deferred.
