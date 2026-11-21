# Feature Specification: ADO Simulator Backlog and Work Item Form

**Feature Branch**: `018-ado-sim-backlog-form`

**Created**: 2026-11-21

**Status**: Draft

**Input**: User description: "018 ado-sim-backlog-form — Phase 2 Option A (SA §22.2, build plan §11).
The backlog tree and the work item form of the ADO simulator: people see each use case's Epic with
its run items and clarification items beneath it, open any item, and act on it in a form: set the
decision with its comment and inputs, answer a clarification, add a comment, read the item's
history, and follow the link to the run's evidence in the platform's console."

## Clarifications

### Decided before this feature (recorded for context)

- Phase 2 Option A: the board is the people's interface; the platform is the only source of truth
  (SA §22.1). 015 built the simulator's API, 016 the engagement layer, 017 sign-in and the board.
- The simulator holds no lifecycle, policy or decision-rights logic (SA §22.2): the form saves
  fields as the signed-in user, exactly as the API does; whether a decision is allowed is decided
  by the platform (016), which answers with a comment and reverts a refused request.
- People decide through one decision field, saved with its comment, and its inputs (root cause,
  reason, rework target, values) in their own fields or as comment lines (016 FR-028). A
  clarification is answered in its own answer field (SA §22.3).
- The board and the backlog-and-form are two features (2026-11-20); this one replaces 017's
  read-only item page with the form.
- Server-rendered pages with Jinja2 and HTMX, inside the simulator (2026-11-20); sign-in, sessions,
  CSRF and escaping as built in 017.

### Session 2026-11-21

- Q: Can people change fields the platform owns (such as an Epic's state) on the form? → A: yes,
  as real ADO; the simulator saves the change and the platform sets it back with a comment (D-12).

## User Scenarios & Testing *(mandatory)*

The actors are the demo users signed in to the simulator's pages (017), who hold platform roles
through 016's identity mapping, and the presenter.

### User Story 1 – Decide a run from the form (Priority: P1)

A person opens a run item (from the board, the backlog or the platform's link), reads what the
platform wrote in it (the decision values offered, what each needs, the reviewer's
recommendation), sets the decision field, the comment and any input fields, and saves. The item
is saved as theirs; within the platform's polling interval the platform's reply appears on the
item as a comment, and the item and its Epic move on.

**Why this priority**: this is how a sign-off happens on the board (016 US2); without the form the
board can only be watched.

**Independent Test**: open a run item awaiting sign-off; set the decision to Pass with a comment;
save; the item's history shows the change by that person; with 016's sync running, a comment
"accepted" appears and the Epic moves to the next column.

**Acceptance Scenarios**:

1. **Given** a run item, **When** the form opens, **Then** it shows the item's title, state, every
   field the form layout names in its section, the description as formatted text, the parent and
   children, the comments and the history.
2. **Given** the decision field, **When** the person chooses a value, **Then** they choose from the
   values the seed declares for that field (a list), not free text.
3. **Given** changed fields, **When** the person saves, **Then** the changes are saved in one update
   attributed to them, with the simulator's validation; the form shows the saved item.
4. **Given** someone else (or the platform) changed the item since the form was opened, **When** the
   person saves, **Then** the save is refused as a conflict, the form shows the current item and
   keeps what the person typed so they can save again.
5. **Given** a refusal by the simulator (an unknown field value, a missing title), **When** they
   save, **Then** the message is shown next to the field and their values are kept.

---

### User Story 2 – Answer a clarification from the form (Priority: P1)

The person addressed by a clarification opens its item, reads the numbered questions the platform
wrote, types the numbered answers in the answer field and saves.

**Why this priority**: clarifications stop runs (016 US4).

**Independent Test**: open a clarification item; type "1. … 2. …" in the answer field; save; the
item's history shows the answer by that person; with 016 running, the run continues and the item
closes.

**Acceptance Scenarios**:

1. **Given** a clarification item, **When** the form opens, **Then** the questions are shown in the
   description and the answer field is a multi-line text box.
2. **Given** an answer, **When** it is saved, **Then** it is saved as the person's change, exactly as
   any other field.

---

### User Story 3 – See the work as a tree (Priority: P2)

A person opens the backlog and sees every item of the board type (each use case's Epic) with its
children beneath it (run items, and their clarification items), each with its id, title, type and
state, expandable and collapsible, filtered by area path.

**Why this priority**: the board shows only Epics; the run and clarification items that people act
on are found here (and through links).

**Independent Test**: with an Epic, two run items under it and a clarification item under one run,
the backlog shows the three levels in order; collapsing the Epic hides its children.

**Acceptance Scenarios**:

1. **Given** items linked by parent and child, **When** the backlog opens, **Then** each top-level
   item (an item of the board type without a parent) is shown with its descendants indented,
   ordered by id, each showing id, type, title and state, and each a link to its form.
2. **Given** a tree, **When** a level is collapsed or expanded, **Then** its children hide or show,
   and the state survives the backlog's refresh.
3. **Given** an area filter (as on the board), **When** it is chosen, **Then** only trees whose top
   item is in that area (or below) are shown.
4. **Given** the backlog open, **When** the platform adds or changes items, **Then** the backlog shows
   it at its next refresh, without a reload (as the board).

---

### User Story 4 – Comments, history and the evidence link (Priority: P2)

On any item, a person adds a comment, reads every comment (the platform's replies included) and
reads the history: each update with who, when, and each changed field from its old to its new
value. A run item's evidence link opens the run in the platform's console.

**Why this priority**: the platform answers on the board with comments (016); the history is how a
person sees that their change was reverted and why; the evidence must be in front of the person
before a sign-off (SA §8.2).

**Independent Test**: add a comment; it appears with the person and time; change a field; the
history shows the old and new values by that person; the evidence link opens the console's page
for the run.

**Acceptance Scenarios**:

1. **Given** an item, **When** a comment is added, **Then** it is saved as the person's comment
   (exactly as the comments API) and shown at the top of the comments, newest first.
2. **Given** an item's history, **When** the form shows it, **Then** each update shows who, when and
   each changed field with old and new values; long values are shortened with a way to see them in
   full; link changes say which item was linked or unlinked.
3. **Given** a field holding a web address (the evidence link), **When** the form shows it, **Then**
   it is a link that opens in a new tab; only http and https addresses become links.
4. **Given** the platform's comment that refused a decision, **When** the person reads it, **Then**
   it is shown as text (never as markup) with its author, the platform's service account.

---

### User Story 5 – Change other fields, and see the platform set them back (Priority: P3)

A person can change any editable field on the form, including fields the platform owns, such as
the Epic's state. The simulator saves the change; the platform sets it back with a comment (016).

**Why this priority**: it is demo moment D-12 (a change without the right is reverted with the
reason) and it is how real ADO behaves; the simulator holds no rule to stop it.

**Independent Test**: change an Epic's state on its form to a later stage; save; the history shows
the change by the person; with 016 running, the next update sets it back by the service account,
and a comment gives the reason.

**Acceptance Scenarios**:

1. **Given** an editable field the platform writes, **When** a person changes and saves it, **Then**
   the simulator saves it like any other field, as real ADO does; the platform sets it back with a
   comment giving the reason (016 FR-017). The simulator carries no list of platform-owned fields.
2. **Given** read-only system fields (id, revision, created and changed by and date), **When** the
   form shows them, **Then** they are not editable.

---

### Edge Cases

- The form is opened for an item of a type the form layout does not describe: every editable field
  of the type is shown in one section.
- A field's value is an identity (assigned to): shown as the display name; edited by choosing a
  seeded user.
- The description holds markup from the platform (paragraphs, lists): shown formatted; any other
  markup (scripts, styles, event attributes, links that are not http or https) is removed.
- A comment or answer longer than the simulator's limit (1 MB): refused with the limit named.
- Two people save the same item: the second gets the conflict of US1-4, not a silent overwrite.
- An item deleted or moved out of the area while the backlog is open: it disappears at the next
  refresh; an open form says the item no longer exists when saved.

## Requirements *(mandatory)*

### Functional Requirements

**Form**

- **FR-001**: The item page at `/{organization}/{project}/_workitems/edit/{id}` MUST become a form
  for signed-in users (017's session, CSRF and escaping rules apply to every action).
- **FR-002**: The form MUST show the fields of the item's type in sections given by a form layout
  in the seed (per type: section titles and field references, in order); fields not in the layout
  are shown in a last "Other fields" section; the layout is data, never names in simulator code.
- **FR-003**: Each editable field MUST use an input that fits its type: a list for fields with
  allowed values in the seed, a single-line box for strings, a multi-line box for plain text and
  history-free HTML fields, a date input for dates, a number input for numbers, a user list for
  identities; read-only system fields are shown as text.
- **FR-004**: A save MUST send only the changed fields, in one update, as the signed-in user,
  checked against the revision the form was opened at (changed = different from the value at that
  revision); an emptied input removes the value; a conflict MUST keep the person's values and show
  the current item.
- **FR-005**: The description and other HTML fields MUST be shown with a safe subset of formatting
  (paragraphs, line breaks, lists, bold, italic, links to http or https); everything else is
  removed before display.
- **FR-006**: Fields holding http or https addresses MUST be shown as links opening in a new tab
  with no referrer and no opener access; other values are never turned into links.

**Comments and history**

- **FR-007**: A person MUST be able to add a comment from the form, saved as the comments API saves
  it, and read all comments newest first, each with author and time, always as plain text (never
  formatted; ADO formats comments: a listed difference).
- **FR-008**: The form MUST show the item's history: every update in order with who, when, each
  changed field with old and new values (long values shortened with the full value available) and
  link changes.

**Backlog**

- **FR-009**: A backlog page at `/{organization}/{project}/_backlogs/backlog` MUST show every item of
  the board type without a parent (items of other types without a parent are not shown), with its descendants as a tree (parent and child links), each row
  with id, type, title and state, linking to the item's form.
- **FR-010**: The backlog MUST support collapsing and expanding levels, an area filter (as the
  board's, in the address), and the board's refresh (same interval, keeping collapsed levels and
  the filter).
- **FR-011**: The board, the backlog and the form MUST link to each other (a navigation bar on every
  page).

**Quality**

- **FR-012**: Every page and action of 017's rules applies: a session for every page, CSRF on every
  change, values escaped, the security headers, logs without values.
- **FR-013**: The form, the backlog and their errors MUST pass the static accessibility checks of
  017 (labels for every input, one main heading, landmarks), and errors MUST be announced next to
  their field.
- **FR-014**: The pages MUST add no dependency beyond those of 017 unless recorded with its licence.

### Key Entities

- **Form layout** (seed data): per work item type, ordered sections, each a title and field
  references.
- **Allowed values** (seed data, from 015): the values a field accepts, shown as a list.
- **Tree row** (view): item, depth, children, collapsed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person signs off a run from the form (open, choose Pass, comment, save) in under one
  minute on the demo, and 100% of form saves are attributed to the signed-in person.
- **SC-002**: With 200 use cases (600 items), the backlog's first view in under 1 second and its
  refresh in under 0.5 seconds at the 95th percentile; the form opens in under 0.5 seconds.
- **SC-003**: In a scripted set of concurrent saves of one item, 100% of the second saves get the
  conflict and keep the person's values; none overwrites silently.
- **SC-004**: A scripted set of hostile values (scripts, event attributes, `javascript:` links,
  style blocks) in titles, descriptions, comments and answers is never executed or rendered as
  markup on any page.
- **SC-005**: The static accessibility checks report no issue on the form, the backlog and their
  error states.
- **SC-006**: With 016's sync running, the full lifecycle of one use case can be driven on the
  simulator's pages alone (the board, the backlog and the form), without the platform's inbox;
  measured by this feature's live walk (registration through a sign-off, a revert and a
  clarification), the rest by the demo rehearsal (020).

## Assumptions

- The seed's form layout covers the demo's three types (Epic, Feature for runs, Task for
  clarifications); Option B's Stories and plan items are out of scope.
- The decision field's allowed values in the seed are the decision values of the platform's tracker
  mapping (016), kept in step by the 016 mapping check (a value the board offers that the mapping
  does not know is reported).
- HTML sanitising uses an allow-list implemented in the simulator (no new dependency), or a small,
  maintained library recorded with its licence (decided in the plan).
- Desktop browsers only, as 017.
