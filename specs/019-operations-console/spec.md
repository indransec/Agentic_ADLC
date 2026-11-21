# Feature Specification: Operations Console

**Feature Branch**: `019-operations-console`

**Created**: 2026-11-21

**Status**: Draft

**Input**: User description: "019 operations-console — Phase 2 Option A (SA §22.4, build plan §11).
The platform's web app reduced to an operations console once the board drives every decision: it
keeps what a work item form cannot show (the evidence viewer with artifact editing before
sign-off, KPIs and the journey, activity, dead letters) and adds the board sync's status
(health metrics, reconciliation results, reconcile now). Decisions, intake, clarification answers,
waivers and escalations are made on the board."

## Clarifications

### Decided before this feature (recorded for context)

- Phase 2 Option A: the board is the people's interface; the platform is the only source of truth
  (SA §22.1). 015–018 built the simulator, the sync and the board's pages; every decision the
  inbox offers can now be made on the board (decision field, clarification answer, an Epic for a
  new use case).
- SA §22.4: the console keeps the evidence viewer (artifacts with agent and human versions,
  artifact editing before sign-off, control results, reviewer findings, prerequisites with result
  and reason, deep-linked from the card), dead letters, sync status and reconciliation results
  with sync health as metrics and a "reconcile now" action, KPIs and the journey view.
- SA §8.2 still holds: a sign-off needs the evidence in front of the person; the card links to it.
- Reconciliation stays manual (2026-11-18): triggered from the console or the CLI, no schedule.
- The inbox stays available until feature 020 (the demo on the board) passes (SA §22.10).
- The web app keeps its stack (Streamlit, feature 007) and its boundary: it calls only the
  platform API.

### Session 2026-11-21

- Q: What decides whether the web app is the inbox or the console? → A: whether the board sync is
  enabled (`ADLC_BOARD_ENABLED`), read by the web app from the platform API; turning the sync off
  brings the inbox back.

## User Scenarios & Testing *(mandatory)*

The actors are the platform's people (signed in to the console with their platform accounts) and
the ADLC CoE (who runs the sync).

### User Story 1 – Read the evidence from the board's link (Priority: P1)

A person about to sign off on the board follows the run item's evidence link and lands on that
run in the console: artifacts (with agent and human versions), the reviewer's findings and
recommendation, control results, prerequisites with result and reason, and the timeline. If the
run is awaiting their sign-off, they can still correct an artifact before signing off. The page
says where to decide and links back to the run's board item.

**Why this priority**: a sign-off without the evidence breaks SA §8.2; the link is the only way
from the card to the evidence.

**Independent Test**: from a run item's evidence link, the console opens on that run (after
sign-in if needed); every evidence section is shown; editing an artifact records a human version;
the page shows "Decide on the board" with a link to the run's work item, and no decision form.

**Acceptance Scenarios**:

1. **Given** a run item's evidence link, **When** a signed-in person opens it, **Then** the console
   shows that run's evidence; **When** the person is not signed in, **Then** after sign-in they
   land on the same run.
2. **Given** a run awaiting a person's sign-off, **When** they edit an artifact, **Then** the edit is
   recorded as a human version, as today (feature 007), and the controls run again.
3. **Given** the board drives decisions, **When** the run page is shown, **Then** it has no decision
   form; it says the decision is made on the board and links to the run's work item.
4. **Given** a run with no board item yet (the sync has not projected it), **When** the page is
   shown, **Then** it says so instead of a broken link.

---

### User Story 2 – Watch the sync and reconcile (Priority: P1)

The CoE opens the sync status page: whether the sync is enabled and the mapping fits, the last
poll and its outcome, the inbound watermark's age, outbound pending and the oldest pending age,
refused board changes by reason, reverted changes, dead-lettered use cases, and the last
reconciliation with its differences. They can reconcile now and re-queue a dead-lettered use case.

**Why this priority**: the sync is the bridge between the board and the platform; when it lags or
refuses, the CoE must see it and act (016 FR-022, FR-025).

**Independent Test**: with the sync running, the page shows each metric; stopping the simulator
makes the watermark age and the last poll outcome change on the next refresh; "Reconcile now"
records a reconciliation whose differences are listed; a person without the CoE role cannot open
the page or act.

**Acceptance Scenarios**:

1. **Given** the CoE, **When** they open sync status, **Then** every health value of 016's
   `/board/health` is shown, with ages in human units and refusals by reason.
2. **Given** the page open, **When** the sync's state changes, **Then** the page shows it at its next
   refresh (the dashboard refresh interval).
3. **Given** "Reconcile now", **When** the CoE confirms it, **Then** a reconciliation runs and its
   result (differences found and corrected, by item and field) is shown.
4. **Given** a dead-lettered use case, **When** the CoE re-queues it, **Then** it is re-queued and
   leaves the list once delivered.
5. **Given** a person without the CoE role, **When** they look for sync status, **Then** it is not
   offered, and the API refuses it if called.
6. **Given** the sync disabled, **When** the page opens, **Then** it says the sync is off and offers
   no action.

---

### User Story 3 – A console, not an inbox (Priority: P2)

When the board drives decisions, the console offers only what the board cannot: the navigation no
longer shows the inbox or the intake form, and the clarification, escalation and waiver pages are
not reachable; each place that offered a decision says it is made on the board and links to the
item. KPIs, the journey, activity, the portfolio, use cases (with ledger verification) and dead
letters stay as they are.

**Why this priority**: two places to decide confuse people and the demo; the board is the
interface.

**Independent Test**: with the board driving decisions, the sidebar lists only the console's pages;
opening a removed page's address shows where to go instead; with it off, the web app is the inbox
as before.

**Acceptance Scenarios**:

1. **Given** the board drives decisions, **When** a person signs in, **Then** they land on the
   console's first page (not the inbox) and the navigation lists the console's pages only.
2. **Given** an old address of the inbox, intake, clarification, escalation or waiver page, **When**
   it is opened, **Then** the page says the action is now on the board, with a link to the board.
3. **Given** the board does not drive decisions, **When** a person signs in, **Then** the web app is
   the inbox exactly as before (feature 007), with the sync status page added for the CoE.

---

### User Story 4 – Switching between inbox and console (Priority: P2)

The web app is the console when the board sync is enabled (`ADLC_BOARD_ENABLED`), and the inbox
when it is not. The web app reads this from the platform API, so one setting decides where people
decide: turning the sync off brings the inbox back (the fallback before feature 020 has proven the
board, or when the board is down).

**Why this priority**: the inbox stays available until the demo on the board passes, and is the
fallback when the board is down.

**Independent Test**: with the sync enabled the web app is the console; with it disabled (and the
API restarted) the web app is the inbox, without code changes; the platform API keeps accepting
every command either way.

**Acceptance Scenarios**:

1. **Given** the console mode, **When** a decision is posted to the API directly, **Then** it is
   still accepted (the API keeps every command; only the web app's offer changes).
2. **Given** the sync enabled, **When** any signed-in person's web app asks the API for the mode,
   **Then** it answers "console" (with the board's address for browsers); **Given** it disabled,
   **Then** "inbox".
3. **Given** the API cannot be asked (an error), **When** the web app starts a page, **Then** it
   keeps the last known mode for the session, or the inbox when none is known, and says so.

---

### Edge Cases

- The evidence link names a run that does not exist or that the person may not see: the page says
  so, as the run page does today.
- The sync status API is unreachable or the sync was never started: the page says so and shows
  the last known values with their time.
- A reconciliation is already running: the action says so and shows the running one.
- A reconciliation finds hundreds of differences: the list is paged or truncated with the count.
- The board's work item address cannot be built (no board link for the run): text instead of a
  link (US1-4).

## Requirements *(mandatory)*

### Functional Requirements

**Evidence (deep links)**

- **FR-001**: The run page MUST open from the board's evidence link (the run in the address) and
  survive sign-in (the person returns to the same run).
- **FR-002**: The run page MUST keep every evidence section of feature 007 (artifacts with
  versions, reviewer findings and recommendation, control results, prerequisites, citations,
  prior rework, clarifications, approvals, waiver, activity, timeline) and artifact editing
  before sign-off, limited as in 007 to runs awaiting the person's own sign-off.
- **FR-003**: In console mode the run page MUST NOT offer a decision; it MUST say the decision is
  made on the board and link to the run's board work item when the platform knows it.

**Sync status**

- **FR-004**: A sync status page MUST show every value of 016's sync health (enabled, mapping fit,
  last poll time and outcome, watermark and its age, outbound pending and oldest pending age,
  dead-lettered use cases, refusals by reason, reverted count, last reconciliation), refreshed at
  the dashboard interval.
- **FR-005**: The page MUST offer "Reconcile now" (with a confirmation) and show the result's
  differences, and re-queue for each dead-lettered use case. It MUST say that this re-queue is for
  board deliveries, distinct from the Dead letters page (platform events).
- **FR-006**: The page and its actions MUST be offered to the CoE role only; the API already
  refuses others (016).

**Console**

- **FR-007**: In console mode the navigation MUST list only the console's pages (run evidence by
  link, use cases, journey, activity, portfolio, dead letters, sync status), and the inbox, intake,
  clarification, escalation and waiver pages MUST say the action is on the board, with a link.
- **FR-008**: Outside console mode the web app MUST behave as feature 007 and 013 built it, plus
  the sync status page for the CoE.
- **FR-008a**: The mode MUST follow whether the board sync is enabled, read through a read-only
  platform API answer available to every signed-in person (the mode and the board's address for
  browsers); no web app setting chooses it. The web app re-reads it at most every 60 seconds, so
  a change takes effect within the API's restart plus 60 seconds; on an error it keeps the last
  known mode (the inbox only when none is known).
- **FR-009**: The platform API MUST be unchanged for every command; the reduction is the web app's
  offer only. Any API addition (for example a run's board work item address, or the mode) MUST be
  read-only.
- **FR-010**: The web app MUST keep its boundary (only the platform API) and rendering rules (agent
  and person text as plain text).
- **FR-011**: No hard-coded board address, organisation or project in code: the board's public
  address comes from settings.

### Key Entities

- **Console mode**: whether the web app is the inbox or the console; it follows the board sync's
  enabled setting (US4).
- **Board link of a run**: the board work item that shows a run, as the sync recorded it (016),
  and the address a browser opens for it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a run item's evidence link, the evidence is on screen in under 3 seconds (signed
  in) for a run with ten artifacts.
- **SC-002**: In console mode, no page of the web app offers a decision, an intake or an answer
  (checked by a sweep of every page), and every removed page points to the board.
- **SC-003**: The sync status page shows a stopped board within one refresh interval plus one poll
  interval, and its recovery likewise.
- **SC-004**: "Reconcile now" from the console runs a reconciliation and shows its differences in
  under 10 seconds for the demo's data (tens of use cases).
- **SC-005**: Outside console mode, every existing web app test still passes unchanged.

## Assumptions

- The CoE is the only operator of the sync, as in 016.
- The board's address for browsers (for links to work items) differs from the address the sync
  uses inside Docker; it is a separate setting.
- Desktop browsers, as feature 007.
