# Feature Specification: ADO Simulator Board

**Feature Branch**: `017-ado-sim-board`

**Created**: 2026-11-21

**Status**: Draft

**Input**: User description: "017 ado-sim-board — Phase 2 Option A (SA §22.2, build plan §11). The
Epic board of the ADO simulator: a web page where demo users sign in and see every Epic in the
column of its state (the terminal stages), with its sub-stage, filtered by area path, refreshing
as the platform moves it; columns are set by the platform, not by drag and drop. Server-rendered
inside the simulator (FastAPI, Jinja2, HTMX). The backlog tree and the work item form are 018."

## Clarifications

### Decided before this feature (recorded for context)

- Phase 2 Option A: the board becomes the people's interface; the platform stays the only source
  of truth (SA §22.1). Feature 015 built the simulator's API, feature 016 the engagement layer
  that keeps the board and the platform in step.
- The simulator holds no lifecycle, policy or decision-rights logic (SA §22.2). Its pages show and
  change work items exactly as its API does; meaning (which column is a terminal, which field is
  the sub-stage) comes from data, never from simulator code.
- Columns are written only by the platform; a person's column change is reverted by the platform
  (016). The board therefore offers no drag and drop (SA §22.2, decided 2026-11-15).
- The board and the backlog-and-form are two features (decision of 2026-11-20); this one is the
  board. The work item form, with the decision, clarification and comment fields, is 018.
- UI technology: server-rendered pages in the simulator's own FastAPI app with Jinja2 templates and
  HTMX (decision of 2026-11-20); no build step, no JavaScript framework.

### Session 2026-11-21

- Q: How do demo users sign in to the pages? → A: all three ways: a personal page password set by
  the operator and stored as a hash; a shared demo password, only when the operator sets one (off by
  default, a warning logged at start); or one of the user's personal access tokens.

## User Scenarios & Testing *(mandatory)*

The actors are the demo users seeded in the simulator (one per platform role, plus the
platform's service account, which never signs in to pages) and the presenter running the demo.

### User Story 1 – Sign in as a demo user (Priority: P1)

A person opens the simulator in a browser, picks who they are from the seeded users and signs in.
Everything they then do on the pages is attributed to that user, exactly as an API call with that
user's token would be. They can sign out and sign in as someone else.

**Why this priority**: every board action is a request whose author matters (016 maps the board
user to a platform role); without sign-in nothing on the board can be attributed.

**Independent Test**: open the board without a session: the sign-in page is shown; sign in as the
product owner; the page header names the product owner; create an Epic from the board; its history
shows it created by the product owner; sign out; the board asks for sign-in again.

**Acceptance Scenarios**:

1. **Given** no session, **When** any page is opened, **Then** the sign-in page is shown, listing
   the seeded users by display name (the service account is not offered).
2. **Given** valid credentials, **When** a user signs in, **Then** a session starts, the header
   shows the user's display name, and every change they make is recorded as theirs.
3. **Given** wrong credentials, an unknown user or the service account, **When** sign-in is tried,
   **Then** it is refused with one message that does not say which part was wrong.
6. **Given** a user with a page password, the shared demo password set, and a valid token, **When**
   they sign in with any one of them, **Then** they are signed in as the user they picked; a
   revoked token or a cleared password no longer works, and the user's open sessions end at once.
4. **Given** a signed-in user, **When** they sign out, **Then** the session ends and every page asks
   for sign-in again.
5. **Given** a session older than its lifetime (default 8 hours from sign-in, not extended by
   use), **When** a page is opened, **Then** sign-in is asked for again.

---

### User Story 2 – See every Epic in its column (Priority: P1)

A signed-in user opens the board and sees one column per state of the Epic type, in the process's
order (the terminal stages, then the closed and removed states), and one card per Epic in the
column of its state. Each card shows the Epic's id, title, sub-stage and who changed it last.

**Why this priority**: this is the screen the demo is presented on (D-1 to D-9 on the board).

**Independent Test**: seed the board with Epics in three different states; the board shows three
cards, each in the column of its state with its sub-stage; an empty column is still shown.

**Acceptance Scenarios**:

1. **Given** the seeded process, **When** the board opens, **Then** it shows one column per Epic
   state, in the process's order, each headed by the state's name and the count of its cards.
2. **Given** Epics in several states, **When** the board opens, **Then** each Epic is one card in
   its state's column, ordered by id, showing id, title, the sub-stage field and the last changer.
3. **Given** a card, **When** it is opened, **Then** the Epic's page opens (in this feature a
   read-only view of its fields, parent, children and history; 018 replaces it with the form).
4. **Given** the closed and removed states, **When** the board opens, **Then** their columns are
   collapsed by default (count shown, cards hidden until expanded), so the active stages fit.
5. **Given** more Epics than fit, **When** a column is long, **Then** it scrolls on its own; the
   board stays usable with 200 Epics.

---

### User Story 3 – The board keeps up with the platform (Priority: P1)

While the board is open, the platform moves Epics between columns and changes their sub-stage
(through the API, 016). The board shows each change without the person reloading the page.

**Why this priority**: the audience watches the lifecycle move on the board; a stale board hides
exactly what the demo is about.

**Independent Test**: open the board; change an Epic's state and sub-stage through the API; within
the refresh interval the card is in the new column with the new sub-stage, without a reload.

**Acceptance Scenarios**:

1. **Given** an open board, **When** an Epic's state, sub-stage or title changes, **Then** the board
   shows it within the refresh interval (default 5 seconds) without a page reload.
2. **Given** a new Epic created by anyone, **When** the board refreshes, **Then** its card appears.
3. **Given** the refresh, **When** nothing changed, **Then** the page does not flicker or lose the
   person's scroll position, filter or expanded columns.
4. **Given** the simulator is briefly unreachable, **When** a refresh fails, **Then** the board keeps
   the last view, shows that it is not current, and recovers on its own.

---

### User Story 4 – Create an Epic from the board (Priority: P2)

A signed-in user creates an Epic from the board with a title, a description and an area path. It
appears on the board; the platform registers it as a use case (016) and moves it to the first
terminal's column.

**Why this priority**: starting a use case from the board is the first demo step on the board
(016 US3); without it the demo starts in the inbox.

**Independent Test**: create an Epic from the board as the business owner; it appears on the
board in the Epic type's first state, created by the business owner, in the chosen area.

**Acceptance Scenarios**:

1. **Given** a signed-in user, **When** they create an Epic with a title, description and area,
   **Then** it is created as that user, exactly as an API create would be, and its card appears.
2. **Given** a missing title or an area that does not exist, **When** they submit, **Then** the form
   shows the simulator's refusal next to the field and keeps what they typed.
3. **Given** the create form, **When** it is opened, **Then** it offers only the area paths that
   exist, defaulting to the one the board is filtered on.

---

### User Story 5 – Filter by area path (Priority: P2)

A user narrows the board to one area path (and the paths under it).

**Why this priority**: several teams' Epics would crowd one board; the demo uses one area, but the
filter is how ADO boards are used (SA §22.2).

**Independent Test**: seed Epics in two areas; filter on one; only its Epics are shown; the filter
survives a refresh and is in the page's address, so a link reopens the same view.

**Acceptance Scenarios**:

1. **Given** Epics in several areas, **When** an area is chosen, **Then** only Epics in that area or
   below are shown, and column counts follow.
2. **Given** a filtered board, **When** it refreshes or is reloaded, **Then** the filter stays.

---

### Edge Cases

- An Epic in a state that the Epic type no longer lists (process changed after seeding): shown in an
  "other" column at the end, never hidden.
- An Epic whose sub-stage field is empty: the card shows no sub-stage line, not an error.
- A title or sub-stage with markup characters: shown as text, never interpreted as HTML.
- Two people create Epics at the same moment: both appear; nothing is lost.
- The board is opened by a user whose session was revoked (sign-out in another tab): the next
  refresh redirects to sign-in rather than showing an error.
- A browser without JavaScript: the board shows (server-rendered) and the manual reload works;
  only the automatic refresh needs JavaScript.

## Requirements *(mandatory)*

### Functional Requirements

**Sign-in**

- **FR-001**: Every page except the sign-in page, its static assets and `/health` MUST require a
  signed-in session; API calls keep using tokens and are unaffected.
- **FR-002**: Users MUST sign in as one of the seeded identities, except the service account, by
  picking the user and giving one of three credentials, all accepted:
  1. **a personal page password**, set by the operator with an `ado-sim` command (per user, or one
     command for every demo user) and stored only as a hash;
  2. **the shared demo password**, only when the operator sets `ADO_SIM_DEMO_PASSWORD` (off by
     default); when it is set the simulator logs a warning at start that anyone with it can sign in
     as any demo user;
  3. **one of the user's valid personal access tokens** (the API credential of 015).
  A credential only ever signs in the user picked. A refusal MUST not reveal which part was wrong,
  nor which kinds of credential exist for that user.
- **FR-003**: A session MUST be a signed, HTTP-only, same-site cookie with a lifetime (default 8
  hours); sign-out MUST end it; the session's identity is the author of every change made in pages.
- **FR-004**: Every page form that changes data MUST be protected against cross-site request
  forgery, including the sign-in form.
- **FR-004a**: Clearing a user's page password or revoking one of their tokens MUST end that user's
  open page sessions at once. Repeated failed sign-ins are not locked out (decided at Gate 2: a
  local demo simulator; every failure is logged with the user and outcome, never the credential).

**Board**

- **FR-005**: The board MUST show one column per state of the board's work item type, in the
  process's order, taken from the seeded process; the type, the card fields and the collapsed
  states MUST be data (the seed file's board settings), never names in simulator code.
- **FR-006**: Each card MUST show the item's id, title, the configured card fields (the sub-stage
  for the demo) and its last changer, as text.
- **FR-007**: The board MUST NOT offer moving cards between columns; a state changes only through
  the API (the platform) or, in 018, the form (and the platform reverts a person's change).
- **FR-008**: The board MUST refresh itself every configured interval (default 5 seconds) without a
  page reload, keeping filter, scroll position and expanded columns, and show when a refresh
  failed. A refresh is silent for screen readers (no live-region announcement); the column counts
  are updated so a reader finds the change on the next visit to a column.
- **FR-009**: The board MUST filter by area path (the path and those under it); the filter MUST be
  part of the page address.
- **FR-010**: A signed-in user MUST be able to create an Epic (title, description, area path) from
  the board; it MUST go through the same validation and history as an API create, attributed to
  that user, and refusals MUST be shown next to the field.
- **FR-011**: A card MUST open the item's page; in this feature a read-only page with its fields,
  parent, children and history (each update with who and when), which 018 replaces with the form.

**Quality and boundaries**

- **FR-012**: Pages MUST render every value as text (escaped), never as markup, including the
  description (shown as plain text in this feature).
- **FR-013**: The pages MUST use only the simulator's own code and data; the platform imports
  nothing from them and they import nothing from the platform (boundary tests of 015 extended to
  templates and static files).
- **FR-014**: The page assets (HTMX and the stylesheet) MUST be served by the simulator itself
  (no external network at demo time), with their licences recorded.
- **FR-015**: Page requests MUST be logged like API requests (operation, identity, status,
  duration), never with field values, passwords or session values.
- **FR-016**: The pages MUST be usable with a keyboard and readable by a screen reader (landmarks,
  headings per column, labelled form fields, visible focus) and at 1280×720 without horizontal
  scrolling of the page (columns may scroll).

### Key Entities

- **Board settings** (seed data): the work item type shown, the fields shown on cards, the states
  whose columns start collapsed, the refresh interval.
- **Page session**: identity, issued time, expiry; held in a signed cookie, revocable by sign-out.
- **Page password**: identity, password hash, set time; set or cleared by the operator command.
  The shared demo password is a setting, never stored; tokens are those of 015.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With 200 Epics, the board's first view is shown within 1 second and each refresh
  within 0.5 seconds on the demo host, at the 95th percentile.
- **SC-002**: A state or sub-stage change made through the API shows on an open board within the
  refresh interval plus 1 second, in 100% of a scripted set of 50 changes.
- **SC-003**: 100% of changes made through the pages carry the signed-in user as author in the
  item's history (checked over every page action).
- **SC-004**: No page is reachable without a session (an automated sweep of every route), and no
  password, token or session value appears in any log line.
- **SC-005**: Automated accessibility checks of the board, the item page and the sign-in page
  report no serious or critical issue.
- **SC-006**: A presenter can show a use case moving from the first to the last column on the
  board without reloading the page.

## Assumptions

- The board shows the Epic type for Option A (board settings in the seed); Features, Stories and
  Tasks appear in the backlog tree of 018.
- The simulator runs on one host for the demo; sessions live in signed cookies, so a restart keeps
  them valid until they expire (sign-out revocations are kept in the simulator's database).
- The refresh is short polling of a board fragment (HTMX), not server push; 5 seconds is enough for
  the demo and keeps the simulator simple.
- The item page in this feature is deliberately read-only; editing fields, decisions, answers and
  comments is 018.
- The shared demo password is a presenter's convenience for rehearsals; the recommended demo set-up
  is personal page passwords (one `ado-sim` command for all demo users).
- Desktop browsers only (the demo is presented on a laptop and a projector).
