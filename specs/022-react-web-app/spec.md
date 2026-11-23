# Feature Specification: Web Application Rebuild

**Feature Branch**: `022-react-web-app`

**Created**: 2026-11-23

**Status**: Draft

**Input**: User description: "Feature 021 react-web-app (number 021 explicitly, short name
"react-web-app", branch 021-react-web-app off feature/sqlite). Rewrite the Phase 1 web application
(currently Streamlit, src/adlc/ui) in React + TypeScript with page-for-page parity, without the 019
operations console (no board mode, no Sync status, no /board calls). Pages: sign-in, Inbox (30 s
refresh), New use case, Use cases (only mine / all, journey, ledger verify), Run (summary bar,
artifacts beside reviewer recommendation, control results and decision form, evidence tabs,
editable artifact grid up to 1,000 rows else read-only with upload, attachments download only,
?run= deep link, stale version reload), Clarification, Escalation, Waiver, Dead letters (re-queue
CoE only), Journey, Activity, Portfolio. Navigation from one config table so console mode can be
added later. Architecture: the ui process stays Python (Starlette) serving the built React files
and proxying /api to adlc-api with unchanged API paths, same origin, no CORS, PUBLIC_PATHS
unchanged. Auth: sign-in also sets an HttpOnly SameSite=Strict session cookie; auth middleware
accepts cookie or bearer; state-changing requests with the cookie need a CSRF header; the token
never reaches browser JavaScript. API routes returning dict[str, Any] get Pydantic response models;
OpenAPI exported and TypeScript types generated, with a freshness test. Rendering rules kept:
agent/person text shown as text only (ban dangerouslySetInnerHTML), statuses as platform words,
attachments download only, every action sends run version. Boundary: only the API client calls
fetch (lint rule replaces test_ui_boundary). Libraries: Vite, React Router, TanStack Query, AG Grid
Community, Plotly.js. Node needed at build time only; runtime stays Python. Tests: Vitest + React
Testing Library + MSW replacing Streamlit AppTest suites, Playwright flows against make local. make
check gains web-lint, web-typecheck, web-test; CI installs Node and pnpm. Procfile.local and
compose ui service updated (multi-stage image, health on /health). Streamlit runs alongside until
parity, then Streamlit, plotly (python), .streamlit and AppTest tests are removed. Docs: ADR, SA §8,
ui README, run-without-docker, user manual."

## Clarifications

### Session 2026-11-23

- Renumbered from 021 to **022** (branch `022-react-web-app`) after analysis: SA §22.10 reserves
  021 for "increments", and `main` uses 015–020. The input above is kept as given.

## Context

Feature 007 (SA §8) gave people one web application for intake, the inbox, run detail with
sign-off, artifact editing and the request forms; feature 013 (SA §12) added the Journey,
Activity, Portfolio and Dead letters pages. That application renders every page on the server and
redraws the whole page on each interaction. This feature rebuilds the same application as a
browser application: pages respond in place, tables and the artifact editor behave like a
desktop grid, and the application can grow without the limits of a server-redrawn page.

The rebuild is a **like-for-like replacement** on the Phase 1 platform (this branch: SQLite and
Phoenix). Every page, action, rule and message that people rely on today stays; nothing about
the lifecycle, the decision rights or the evidence changes. The feature 019 operations console
(board mode, Sync status, "decide on the board") is not part of this branch and is out of scope,
but the navigation is built so that it can be added later without restructuring.

Because the application now runs in the browser, two things that the server-side application
handled implicitly must be made explicit: how the person's session is held so that page scripts
can never read it, and a described, checked contract for every platform answer the application
reads.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A person signs in and their session stays out of reach (Priority: P1)

A person opens the application, signs in with their account and password and lands on their
Inbox. Their session is held by the browser in a way no page script can read. Signing out, or the
session expiring, returns them to sign-in. A link to a run (`?run=<run id>`) opened by someone who
is not signed in shows sign-in first and then opens that run.

**Why this priority**: nothing else works without sign-in, and moving the application into the
browser is only acceptable if the session is at least as safe as it is today (constitution XI).

**Independent Test**: sign in, check that the session cannot be read from page scripts or browser
storage, sign out, and open a run link while signed out.

**Acceptance Scenarios**:

1. **Given** a valid account, **When** the person signs in, **Then** the Inbox opens, the sidebar
   shows their name and roles, and the environment badge shows when the environment is set.
2. **Given** a wrong password, **When** the person signs in, **Then** a message says the account
   or password is wrong, without saying which.
3. **Given** a signed-in person, **When** any page script inspects cookies, local storage or
   session storage, **Then** no session credential is found.
4. **Given** a session that has expired, **When** the person takes any action, **Then** they are
   returned to sign-in with a message, and nothing they typed is sent with the expired session.
5. **Given** a person not signed in, **When** they open `?run=<run id>`, **Then** sign-in is shown
   and, after signing in, the Run page opens on that run.
6. **Given** a request that changes something and arrives from another site using the person's
   browser session, **When** the platform receives it, **Then** it is refused and nothing changes.
7. **Given** a tool, test harness or pilot process that reaches the platform with its own
   credential as today, **When** it calls the platform, **Then** it works unchanged.

---

### User Story 2 - An approver decides on a run with full context (Priority: P1)

An approver opens a run from the Inbox or a link. The Run page shows a summary bar (run, version,
terminal and spec version, state and final status, due time and overdue flag, model cost), the
artifacts beside the reviewer recommendation, the control results with their counts and the
decision form, and the other run sections as tabs: prerequisites, citations, prior rework,
clarifications, approvals, waiver, activity, timeline and evidence. The decision form offers only
what the platform says this person may decide, with the fields the chosen outcome needs.

**Why this priority**: deciding on runs is the core of D-1, D-2, D-3 and D-5; the demo cannot run
without it.

**Independent Test**: on a run awaiting decision, pass it; on another, send it to rework with a
comment and root cause; check each decision is recorded and the page reloads with the new state.

**Acceptance Scenarios**:

1. **Given** a run awaiting the person's decision, **When** they open it, **Then** every section
   listed above is present, and each tab shows its count when it has content.
2. **Given** the decision form, **When** the person chooses an outcome, **Then** only the fields
   the platform lists for that outcome appear (comment, root cause, owning terminal, required and
   typed fields, alternative route), and a reason is asked for when the choice differs from the
   reviewer's recommendation.
3. **Given** the run changed after the person opened it, **When** they submit a decision, **Then**
   the page reloads with "This run changed since you opened it" and nothing is recorded.
4. **Given** a blocked run, **When** it is opened, **Then** the page says it is blocked by an
   unmet prerequisite and the person can terminate it if they have the right.
5. **Given** controls being re-run or a waiver pending, **When** the page is open, **Then** the
   form says so and deciding waits as it does today.
6. **Given** a person with no decision on the run, **When** they open it, **Then** the page says
   so and shows no form.

---

### User Story 3 - Approvers edit artifacts before approving (Priority: P1)

Before signing off, an approver edits an artifact's table in place, saves it, sees its history,
uploads a spreadsheet to replace it, and attaches files. Tables up to 1,000 rows are editable in
the page; larger ones are read-only, with upload offered.

**Why this priority**: artifact editing before sign-off is part of the decision (007 User Story 3)
and is the hardest part of the page to rebuild.

**Independent Test**: edit and save cells in a 1,000-row artifact; open a 1,001-row artifact and
check it is read-only with upload offered; upload a spreadsheet; attach a file and download it.

**Acceptance Scenarios**:

1. **Given** an artifact table of up to 1,000 rows, **When** the person edits cells and saves,
   **Then** the new version is stored, the history shows it, and the run version shown is updated.
2. **Given** an artifact table of more than 1,000 rows, **When** it is shown, **Then** it is
   read-only and spreadsheet upload is offered.
3. **Given** a saved edit, **When** the save is answered as stale, **Then** the page reloads with
   the stale message; the unsaved edit is discarded, and the message tells them to check the run
   and apply it again.
4. **Given** an attachment of any type, **When** the person opens it, **Then** it is offered for
   download only and never shown inline.

---

### User Story 4 - Requests reach the right person and are answered in the application (Priority: P2)

A business owner submits a new use case. People answer clarifications (D-9), complete escalations
(D-4) and decide waivers (D-5) on their own pages, opened from the Inbox. The Inbox lists every
item waiting for the person, oldest first, grouped as today (including change requests and
proposed events, D-7), refreshes every 30 seconds and on demand, and opens each item on its page.

**Why this priority**: these complete the demo path; they are simpler pages than the Run page.

**Independent Test**: submit a use case, answer a clarification, complete an escalation, decide a
waiver, record a change-request decision and a proposed-event decision; each item leaves the
Inbox.

**Acceptance Scenarios**:

1. **Given** the intake form, **When** the person submits a name and description, **Then** the
   use case is created and the Use cases page confirms it; a field the platform refuses shows its
   reason beside that field.
2. **Given** an item waiting in the Inbox, **When** 30 seconds pass or the person refreshes,
   **Then** the list is reloaded without losing what they are typing elsewhere on the page.
3. **Given** a clarification, escalation or waiver, **When** the person completes its form,
   **Then** the action is recorded and the item leaves the Inbox.
4. **Given** a person who may not complete an escalation, **When** they open it, **Then** the
   page says so and offers no action.

---

### User Story 5 - People follow delivery and check evidence (Priority: P2)

People follow use cases: the Use cases page ("only mine" or all) with each use case's runs,
times and cost and ledger verification; the Journey page (lanes per terminal, a bar per run,
arrows for reworks, reroutes, exceptions, events and re-entry, the KPI strip, escalations and
exceptions) refreshing on the configured interval (D-8); the Activity feed with filters by use
case, terminal, actor and step that survive refreshes; and Portfolio with KPIs across use cases by
risk tier and status.

**Why this priority**: D-8 and evidence checks depend on these views; they are read-only and
lower risk.

**Independent Test**: open each page on demo data; verify a use case's ledger; set Activity
filters and wait for a refresh.

**Acceptance Scenarios**:

1. **Given** a use case, **When** the person verifies its ledger, **Then** the result says how
   many records were checked or how many breaks were found.
2. **Given** the Journey page, **When** the refresh interval passes, **Then** lanes, arrows and
   KPIs update without a full page reload and without losing the selected use case.
3. **Given** Activity filters, **When** the feed refreshes, **Then** the filters are kept.
4. **Given** statuses, outcomes and risk tiers, **When** they are shown, **Then** each uses the
   platform's own word and colour for known values, and any other value is plain text.

---

### User Story 6 - The CoE handles dead letters (Priority: P3)

A CoE person lists dead letters with attempts, error and re-queue count, opens a payload and its
re-queue history, and re-queues an event. Others see that dead letters are handled by the CoE.

**Why this priority**: an operations page used rarely in the demo.

**Independent Test**: as CoE, re-queue a dead letter; as another role, open the page.

**Acceptance Scenarios**:

1. **Given** a CoE person, **When** they re-queue an event, **Then** the platform records it and
   the list updates.
2. **Given** a person without the role, **When** they open the page, **Then** they see the notice
   and no action; if the action were sent anyway, the platform refuses it.

---

### User Story 7 - The platform team runs, checks and retires the old application (Priority: P3)

Developers and operators run the platform locally without containers and in containers exactly
as today, with the rebuilt application in place of the old one. The single check command also
checks the application's code and tests and fails if the platform's described answers and the
application's expectations drift apart. The old application runs alongside until every page is
shown to match, and is then removed with its tests and dependencies.

**Why this priority**: needed to finish the feature, not to demonstrate it.

**Independent Test**: start the platform both ways; change a platform answer's shape without
updating the description and see the check fail; after cutover, confirm the old application and
its dependencies are gone.

**Acceptance Scenarios**:

1. **Given** a fresh checkout with the documented prerequisites, **When** the developer runs the
   local start command, **Then** the platform and the rebuilt application start, and the
   application is reachable on the same port as today.
2. **Given** the containers, **When** they start, **Then** the application's health check passes
   and the platform's own services are unchanged.
3. **Given** a platform answer whose shape changed, **When** the check runs, **Then** it fails
   until the description and the application are updated.
4. **Given** the parity checklist is complete, **When** the old application is removed, **Then**
   no page, test scenario or demo step depends on it.

---

### Edge Cases

- Agent or person text containing markup, scripts or very long lines (intake, comments, reasons,
  findings, questions, answers, file names, artifact cells) is shown as literal text, wrapped, and
  never interpreted; it never appears inside a control's label.
- Attachments that a browser could render (HTML, SVG, PDF, images) are still download only.
- The platform cannot be reached: each page says so and keeps what the person typed; refreshes
  retry on their interval rather than piling up.
- The session is ended in another tab: the next action in this tab returns to sign-in.
- Two people act on the same run: the second gets the stale message (User Story 2, scenario 3).
- A run link with an unknown run id or no run: the page says the run was not found and links back.
- Browser back, forward and reload keep the person on the same page, run and filters.
- An artifact of exactly 1,000 rows is editable; 1,001 is read-only.
- A request that changes something but lacks the cross-site protection is refused, even with a
  valid session.
- Hiding an action from someone who may not take it is a convenience; the platform still refuses
  it if sent.

## Requirements *(mandatory)*

### Functional Requirements

**Pages and parity**

- **FR-001**: The application MUST provide every Phase 1 page with the behaviour it has today:
  sign-in, Inbox, New use case, Use cases, Run, Clarification, Escalation, Waiver, Dead letters,
  Journey, Activity and Portfolio (`src/adlc/ui/README.md` on this branch is the reference).
- **FR-002**: Navigation MUST be defined in one place listing each page's section (Work, Delivery,
  Insights, Operations), title and whether it appears in the sidebar; Run, Clarification,
  Escalation and Waiver MUST open from other pages, not the sidebar. Adding a page or a mode later
  MUST need only an entry there and the page itself.
- **FR-003**: The application MUST keep the current page, the open run (`?run=`), the selected use
  case and Activity filters in the address, so reload, back, forward and shared links work.
- **FR-004**: The Inbox MUST refresh every 30 seconds and on demand; Journey MUST refresh on the
  configured dashboard interval; refreshes MUST NOT discard input the person is typing.
- **FR-005**: The decision form MUST be built only from what the platform returns for the run
  (outcomes, root causes, owning terminals, required and typed fields, alternatives, the reviewer's
  recommendation); the application MUST NOT contain any terminal, control, role, outcome or
  threshold value (constitution I).
- **FR-006**: Every action on a run MUST send the run version the person saw; a stale answer MUST
  reload the page with the stale message and record nothing.
- **FR-007**: The artifact editor MUST allow in-page editing, adding and removing rows of tables
  up to 1,000 rows and MUST
  show larger tables read-only with spreadsheet upload offered; history, spreadsheet upload and
  file attachment MUST work as today.
- **FR-008**: Errors returned by the platform MUST be shown in plain words; a refusal about a
  specific field MUST be shown beside that field.
- **FR-009**: The out-of-scope console pages (board mode, Sync status, "decide on the board") MUST
  NOT be built, and the application MUST NOT call any board operation.

**Rendering safety (constitution XI)**

- **FR-010**: Text written by agents or people MUST be shown only as literal text, never
  interpreted as markup, and never placed in a control's label. The code MUST be checked
  automatically so that no page can insert raw markup.
- **FR-011**: A status badge MUST show the platform's own word and colour for a known state,
  outcome, status or risk tier; any other value MUST be plain text.
- **FR-012**: Attachments MUST be offered for download only, never shown inline.

**Session and boundary (constitution XI)**

- **FR-013**: After sign-in, the person's session credential MUST be held by the browser in a form
  that page scripts cannot read, and MUST NOT be stored in browser storage or the address.
- **FR-014**: Every request that changes something and relies on the browser-held session MUST
  carry a cross-site request protection that another site cannot supply; requests without it MUST
  be refused.
- **FR-015**: Existing ways of calling the platform with a credential (tools, tests, pilot
  processes) MUST keep working unchanged.
- **FR-016**: The set of operations reachable without a session MUST stay exactly as today
  (health and sign-in); serving the application's own files MUST NOT add to it.
- **FR-017**: The application MUST be served from the same address as the platform operations it
  calls, so no cross-origin access to the platform is opened. The platform's operations and their
  addresses MUST stay unchanged.
- **FR-018**: Only one part of the application MUST talk to the platform; this MUST be checked
  automatically (it replaces today's boundary test).
- **FR-019**: Signing out MUST end the session on the platform and in the browser.

**Platform contract**

- **FR-020**: Every platform operation the application uses MUST describe the shape of its answer,
  and the application MUST use that description for what it reads.
- **FR-021**: The check MUST fail when the description and the application's copy of it differ.

**Running, checking and cutover**

- **FR-022**: Running the platform MUST need no new kind of runtime service: the application is
  served by the existing application process; building the application is the only new
  prerequisite, and it is documented.
- **FR-023**: The local start command and the container setup MUST both start the rebuilt
  application on the existing port and setting (`ADLC_UI_PORT`), with a health check.
- **FR-024**: The single check entry point MUST lint, type-check and test the application, and CI
  MUST run it.
- **FR-025**: Every scenario covered by today's application tests MUST have an equivalent test
  for the rebuilt application, plus end-to-end tests for sign-in, intake, sign-off, artifact edit
  and an expired session run against the locally started platform.
- **FR-026**: The old application MUST stay runnable alongside until a page-by-page parity
  checklist is complete; then it, its tests, its settings files and its dependencies MUST be
  removed.
- **FR-027**: The architecture (SA §8), the application README, the run-without-containers guide
  and the user manual MUST describe the rebuilt application; the decision to rebuild and the
  session model MUST be recorded as an architecture decision.

**Usability baseline**

- **FR-028**: Every page MUST be usable with the keyboard alone, every control MUST have a visible
  label, and status MUST NOT be shown by colour alone.
- **FR-029**: The application MUST work in the current desktop versions of the major browsers.

### Key Entities

- **Browser session**: the signed-in person's session as held by the browser; unreadable by page
  scripts; ends at sign-out or expiry; paired with a cross-site request protection value.
- **Page registry**: the one list of pages with section, title, sidebar visibility and how each is
  opened; the place a later console mode plugs in.
- **Platform contract**: the described shape of every answer the application reads, kept in step
  with the application by the check.
- **Parity checklist**: one row per page and action, with the old and new behaviour and the test
  that shows they match; the condition for removing the old application.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The Phase 1 demo script (D-1 to D-9) can be walked end to end in the rebuilt
  application with no step needing the old application.
- **SC-002**: 100% of the parity checklist rows pass, and every scenario in today's application
  tests has a passing equivalent.
- **SC-003**: In a signed-in browser, no session credential is readable by page scripts or found
  in browser storage or the address (verified by an automated test).
- **SC-004**: 100% of changing requests sent from another site with a valid session are refused.
- **SC-005**: 100% of the markup and script samples in the rendering tests are shown as literal
  text.
- **SC-006**: All existing platform test suites for tools, pilots and scenarios pass with no
  change to how they authenticate.
- **SC-007**: On demo data, each page shows its content within 2 seconds of opening, and editing
  and saving a 1,000-row artifact table completes within 5 seconds.
- **SC-008**: A change to the shape of a platform answer that is not reflected in the application
  fails the check every time.
- **SC-009**: A developer following the updated guide starts the platform locally with one command
  after installing the one new documented prerequisite.

## Assumptions

- Scope is the Phase 1 application on this branch (`feature/sqlite`); the 019 operations console
  exists only on `main` and is not ported. The feature number 022 avoids clashing with `main`'s
  015–020 and with 021, which SA §22.10 reserves for increments.
- The platform's decision rights, roles and session lifetime stay as they are; the platform keeps
  enforcing every rule, and the application only hides actions as a convenience.
- Sessions are the platform's existing local-account sessions; how the browser holds them changes,
  not how they are issued or expire.
- The technology choices named in the input (libraries, test tools, build tooling) are carried to
  `/speckit-plan`, where their licences are recorded (constitution VIII); this spec stays
  technology-neutral.
- Building the application needs a toolchain other than Python. This departs from constitution
  VIII ("Python first") and from this branch's all-Python infrastructure goal, and must be
  justified in the plan's Complexity Tracking or by an amendment before Gate 2.
- The rebuild adds no new demo moment; it re-delivers D-1 to D-9 through the application they are
  shown in (constitution XII). Visual design keeps today's neutral light theme, system fonts and
  one accent colour.
- Desktop browsers only; mobile layouts are out of scope.
- Data is synthetic (SA C-2); no new data is stored by the application.
