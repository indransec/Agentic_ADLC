# Feature Specification: ADO Simulator API

**Feature Branch**: `015-ado-sim-api`

**Created**: 2026-11-20

**Status**: Draft

**Input**: User description: "015 ado-sim-api — Phase 2 Option A, feature 015 (SA §22.2 as
updated on branch docs/phase2-option-a; build plan §11). An Azure DevOps (ADO) simulator that
stands in for Azure DevOps Boards so the platform can later be driven from a board. This feature
delivers only the simulator's ADO-compatible REST API subset, not its UI and not the platform
side. Scope: work items create, get, update (JSON Patch with `test /rev` optimistic concurrency)
and batch get; relations (parent/child, predecessor/successor); a WIQL query subset sufficient for
the engagement layer (by type, state, area path, changed since a date, ids); work item updates
and revisions history (every change readable in order, nothing lost between reads); comments;
classification nodes (Area Paths); identities (demo users mapped later to platform roles through
the tracker mapping; local sign-in with personal access token style auth). The simulator holds no
lifecycle, policy or decision-rights logic; it accepts any field changes a caller with access
makes and records who made them. It has its own data store and shares no code, data or specs with
the platform. Where it differs from real ADO, real ADO wins; it is the only contract reference for
now (no ADO organisation available), so the contract is published (OpenAPI description) with
contract fixtures the platform's adapter tests will use in feature 016. Demo users and a demo
project/area path can be seeded. Supports demo moments indirectly (D-12, D-13 via later
features). Out of scope: board/backlog/form UI (017, 018), the platform adapter and sync (016),
webhooks."

## Clarifications

### Decided before this feature (recorded for context)

- Phase 2 is delivered as Option A first: the board becomes the user interface while the
  platform's lifecycle logic stays as built (SA §22, decisions of 2026-11-20). This feature is the
  first of six Option A features (015–020, build plan §11).
- The simulator lives in this repository as its own project with its own data store; it shares
  no code, data or specs with the platform and holds no lifecycle, policy or decision-rights
  logic (SA §22.2; constitution VII as proposed in 1.2.0).
- The simulator is the only reference for the ADO contract until a real ADO organisation is
  available; where it differs from real ADO, real ADO wins (SA §22.2 fidelity rule).
- People's decisions will be carried by one decision field (`Custom.AdlcDecision`) and the board
  column is written only by the platform (SA §22.3). Both are ordinary fields to the simulator; it
  attaches no meaning to them.
- Inbound changes are read by polling revisions, not webhooks (SA §22.3).

### Session 2026-11-20

- Q: How should the board show which terminal a use case's Epic is in? → A: The Epic type has
  one state per terminal stage, defined in the seed file (for example "T0 Intake" … "T9
  Retirement", "Closed"); the platform moves an Epic by setting its state, as ADO boards map
  columns to states; the run's sub-stage is a custom field (`Custom.AdlcSubStage`). No
  board-column field or board-configuration API is simulated.
- Q: Which ADO process does the seed follow? → A: The Agile process (Epic, Feature, User Story,
  Task, Bug with New, Active, Resolved, Closed and Removed), with the Epic's states replaced by
  the terminal stages and the custom fields features 016–018 need; all of it in the seed file.
- Q: What is the contract derived from, with no ADO organisation available? → A: Microsoft's
  published REST API reference for ADO 7.1: the subset's operations, parameters and shapes are
  taken from it, and the contract tests check the simulator against that subset. (Plan, 2026-11-20:
  Microsoft's machine-readable specification repository no longer exists, so the subset's contract
  is written from the 7.1 reference pages on Microsoft Learn, each operation citing its page; see
  research R-01.)
- Q: How are personal access tokens created and revoked? → A: By an operator command that issues
  a token for an identity (shown once, stored only as a hash) or revokes it; the seed file holds
  identities but no tokens, so no token is ever in the repository.
- Gate 2 (2026-11-20): the contract-source change (research R-01) is accepted; the gaps below
  found by the review checklist are closed in the requirements (link atomicity, token expiry,
  input limits, threat model, api-version, error policy, operator access).

## User Scenarios & Testing *(mandatory)*

The platform will drive the lifecycle from a board (Option A). Before any platform code can talk
to a board, there has to be a board service that behaves like Azure DevOps Boards for the
operations the platform needs, keeps every change with who made it, and publishes that contract
so the platform's adapter (feature 016) can be built and tested against it. The callers in this
feature are API clients: the platform's service account (later, the adapter) and demo users
(later, through the simulator's UI in features 017 and 018); here they are exercised directly.

### User Story 1 – Create, read and update work items (Priority: P1)

A client creates an Epic for a use case and child items for its terminal runs, reads them back
singly or in a batch, and changes their fields with a JSON Patch document. When the client sends
`test /rev` with the revision it last read and someone else has changed the item since, the
update is refused, so no change silently overwrites another.

**Why this priority**: every later feature (adapter, board, form, demo) reads and writes work
items; without this there is nothing to build on.

**Independent Test**: with a seeded project, create an item, read it, update two fields with a
patch, read revision 2, then send a patch with a stale `test /rev` and see it refused with the
current revision unchanged.

**Acceptance Scenarios**:

1. **Given** a seeded project, **When** a client creates a work item of a known type with a
   title, area path and custom fields, **Then** it gets back the item with a new id, revision 1,
   every field it set, and system fields (creator, created and changed date, state).
2. **Given** an item at revision 3, **When** a client sends a patch with `test /rev` = 3 and two
   field changes, **Then** the item is at revision 4 with both changes, made by that client.
3. **Given** an item at revision 4, **When** a client sends a patch with `test /rev` = 3,
   **Then** the update is refused as a conflict and the item stays at revision 4.
4. **Given** ten items, **When** a client asks for eight of them by id in one request with a
   chosen set of fields, **Then** it gets those eight with only those fields, in the order asked.
5. **Given** a work item type whose allowed states are defined, **When** a client sets a state
   the type does not allow, or a field that does not exist, **Then** the update is refused with
   the reason and nothing changes.
6. **Given** an Epic in the state of one terminal stage, **When** a client sets its state to the
   next terminal stage and its sub-stage field, **Then** the Epic is in the new state with the
   new sub-stage at the next revision (the board, feature 017, shows the state as the column).

---

### User Story 2 – Read every change, in order, with who made it (Priority: P1)

A client that reads changes periodically (the platform's inbound sync, later) asks what changed
since its last read and gets every change, including intermediate ones, each with its revision,
the fields that changed (old and new values), who changed it and when. A change the client made
itself can be told apart from a person's change.

**Why this priority**: the platform must never miss or misattribute a person's board change
(SA §22.3: inbound sync reads revisions, not only current state, and excludes its own service
account).

**Independent Test**: change one item three times as two different users between two reads; the
second read returns all three changes in order, each attributed to the right user, with old and
new values.

**Acceptance Scenarios**:

1. **Given** an item changed three times since a client's last read, **When** the client reads
   the item's updates, **Then** it gets three updates in revision order with each changed field's
   old and new value, the changer and the time.
2. **Given** an item, **When** a client reads a specific past revision, **Then** it gets the item
   exactly as it was at that revision.
3. **Given** changes made by the service account and by demo users, **When** a client reads the
   updates, **Then** every update names its changer's identity, so the service account's own
   changes can be excluded.
4. **Given** a client's last read at a known time, **When** it queries for items changed since
   then (User Story 3), **Then** every item with any change after that time is returned, even if
   it changed again since.

---

### User Story 3 – Query work items (WIQL subset) (Priority: P1)

A client finds the items it needs with a query: by work item type, state, area path, a field
value, items changed since a date, or a list of ids, ordered by changed date or id. The query
returns the matching ids, which the client then reads in a batch, as in ADO.

**Why this priority**: the adapter finds changed items and the board, backlog and reconciliation
list items through queries.

**Independent Test**: seed items of three types in two area paths with different states; each
supported query form returns exactly the expected ids in the expected order.

**Acceptance Scenarios**:

1. **Given** items of several types and states, **When** a client queries for Epics in a given
   state under an area path, **Then** it gets exactly the matching ids.
2. **Given** items changed at known times, **When** a client queries for items changed at or
   after a time, ordered by changed date, **Then** it gets every such item once, in that order.
3. **Given** a query using a construct outside the supported subset, **When** the client sends
   it, **Then** it is refused with a reason naming the unsupported construct, never silently
   answered with a partial or wrong result.

---

### User Story 4 – Link work items (Priority: P2)

A client links a terminal run's item to its use case's Epic as a child, links one item as the
successor of another, removes a link, and reads an item with its links; it can also find an
item's children through a query.

**Why this priority**: the Option A board model is an Epic per use case with child items per run
and per clarification (SA §22.3); predecessor and successor links show routing order.

**Independent Test**: create an Epic and two children, link them, read the Epic with relations,
remove one link and read again; a second parent for the same child is refused.

**Acceptance Scenarios**:

1. **Given** an Epic and an item, **When** a client adds a parent link from the item to the Epic,
   **Then** both items show the link (child on the Epic, parent on the item) and each revision
   increases.
2. **Given** an item that already has a parent, **When** a client adds a second parent, **Then**
   it is refused.
3. **Given** a chain A → B → C of parents, **When** a client makes A a child of C, **Then** it is
   refused as a cycle.

---

### User Story 5 – Comment on work items (Priority: P2)

A client adds a comment to an item and lists its comments, newest first or oldest first, each with
its author and time. The platform will use comments to explain a refused or reverted change
(D-12) and people use them alongside decisions.

**Why this priority**: needed by feature 016 to explain reverted changes and by 018's form.

**Independent Test**: add three comments as two users and list them in both orders with authors.

**Acceptance Scenarios**:

1. **Given** an item, **When** a client adds a comment, **Then** the comment is stored with its
   author and time and the item's comment count increases.
2. **Given** comments by two users, **When** a client lists them, **Then** it gets all of them in
   the requested order with authors.

---

### User Story 6 – Identities and access (Priority: P2)

Every request is made by a known identity: a demo user or the platform's service account,
authenticated by its personal access token. A request without a valid token is refused. Clients
can list identities and resolve one by name, so the platform can map a board user to a platform
person (feature 016).

**Why this priority**: every change must be attributed to a known identity, or the platform
cannot check decision rights (SA §22.3) or exclude its own changes.

**Independent Test**: issue a token for a demo user with the operator command, call the API with
no token, a wrong token, a revoked token and the valid one; only the valid one is answered; the
change made with it names its identity.

**Acceptance Scenarios**:

1. **Given** a request without a token or with an unknown or revoked token, **When** it reaches
   any API operation, **Then** it is refused as unauthenticated and nothing changes.
2. **Given** a demo user's valid token, **When** the user changes an item, **Then** the change
   records that user as the changer.
3. **Given** seeded identities, **When** a client lists identities or looks one up by its unique
   name, **Then** it gets the identity's id, display name and unique name.
4. **Given** a seeded identity, **When** an operator issues a token for it, **Then** the token is
   shown once and works; **When** the operator revokes it, **Then** the next request with it is
   refused.

---

### User Story 7 – Seeded organisation, project, area paths and process (Priority: P2)

An operator seeds (or resets) the simulator with one organisation and project, its area paths,
the work item types with their allowed states and custom fields, the demo users and the service
account, from a seed file (tokens are issued separately, US6). Clients can read the area path tree and the types,
states and fields.

**Why this priority**: the demo, the tests of later features and the contract fixtures all start
from a known board.

**Independent Test**: reset from the seed file, then read the area path tree, the work item types
with their states, and the identities; all match the file; data written before the reset is gone.

**Acceptance Scenarios**:

1. **Given** a seed file, **When** an operator seeds an empty simulator, **Then** the project,
   area paths, types, states, custom fields and identities exist as described, and no identity
   has a token until one is issued.
2. **Given** a simulator with data, **When** the operator resets it, **Then** only the seeded
   content remains; a reset is refused unless explicitly confirmed.
3. **Given** a seeded simulator, **When** it restarts, **Then** every work item, revision,
   relation and comment is still there.

---

### User Story 8 – A published contract with fixtures (Priority: P2)

The simulator publishes a machine-readable description of every operation it supports, and a set
of contract fixtures (request and response examples for each operation, including refusals) that
the platform's adapter tests use in feature 016. A list of known differences from real ADO is
kept with the contract.

**Why this priority**: the simulator is the only contract reference for now (SA §22.2); the
adapter must be built against a published contract, not against the simulator's code.

**Independent Test**: every fixture replayed against a freshly seeded simulator gets the recorded
response (status and body shape); the description lists exactly the operations the simulator
serves.

**Acceptance Scenarios**:

1. **Given** a running simulator, **When** a client fetches the contract description, **Then**
   it lists every supported operation with its parameters, bodies and responses.
2. **Given** the contract fixtures and a freshly seeded simulator, **When** each fixture's
   request is replayed, **Then** the response matches the fixture.
3. **Given** an operation of the ADO REST API outside the subset, **When** a client calls it,
   **Then** it is refused as not found or not supported, and the operation is absent from the
   description.

### Edge Cases

- Two clients update the same item at the same time with the same `test /rev`: exactly one wins;
  the other is refused and can re-read and retry.
- A patch mixes valid and invalid operations: the whole patch is refused; no partial change.
- A patch changes nothing (same values): no new revision is created.
- A batch get names an id that does not exist: handled as ADO does (the error policy chosen by the
  caller), never a silent omission.
- A batch get or query result is larger than the ADO limits (200 items per batch, 20,000 ids per
  query): refused or truncated as ADO does, and documented in the contract.
- A changed-since query whose time equals a change's time: that change is included (no gap
  between two reads that use the previous query's `asOf`, the latest changed date that query
  saw).
- Field values with text, numbers, dates, identities and HTML: stored and returned unchanged; the
  simulator never renders or interprets them (rendering is the UI features' concern).
- An item is linked to itself, or a link to a missing item is added: refused.
- A demo user and the service account change the same item between two reads: both updates are
  returned, each with its own changer.
- A token is revoked while a client is using it: the next request is refused.

## Requirements *(mandatory)*

### Functional Requirements

**Work items (US1)**

- **FR-001**: The simulator MUST create a work item of a defined type with field values supplied as
  a JSON Patch document, assign a new id and revision 1, and set the system fields (type, title,
  state, area path, created by and date, changed by and date, revision).
- **FR-002**: The simulator MUST return a work item by id, optionally limited to named fields and
  optionally expanded with its relations, and MUST return several items by id in one request in
  the order asked (at most 200 per request, as ADO; more is refused with `400`). With error policy
  `Fail` (the default) one missing id refuses the whole request with `404`; with `Omit` the
  missing ids are left out and the others returned in order.
- **FR-003**: The simulator MUST apply a JSON Patch update (add, replace, remove and test
  operations on fields and relations) atomically: either every operation applies and the item's
  revision increases by one, or nothing changes and the reason is returned.
- **FR-004**: A `test` operation on `/rev` MUST make the update conditional on the item still being
  at that revision; otherwise the update is refused as a conflict and the response carries the
  current revision.
- **FR-005**: The simulator MUST refuse fields that do not exist for the item's type and states
  the type does not allow, with a reason; it MUST NOT enforce any other rule about which values or
  transitions are allowed (it holds no lifecycle, policy or decision-rights logic). Any allowed
  state may follow any other.
- **FR-006**: Custom fields (`Custom.*`), including the decision field (`Custom.AdlcDecision`) and
  the sub-stage field (`Custom.AdlcSubStage`) the platform will use, MUST be declared in the
  seeded process and then behave like any other field: stored, versioned and queryable, with no
  meaning attached by the simulator. A work item's board column is its state (SA §22.3, as ADO
  boards map columns to states); no separate board-column field is simulated.

**History (US2)**

- **FR-007**: Every change MUST produce exactly one update record with the new revision, each
  changed field's old and new value, relation changes, the changer's identity and the change
  time; updates MUST be readable per item in revision order and never altered or removed.
- **FR-008**: The simulator MUST return any past revision of an item as it was at that revision.
- **FR-009**: Changed dates MUST be taken from the simulator's own clock and strictly increase in
  the order changes are committed, across all items; a query's `asOf` MUST be the latest changed
  date the query could see. A reader that asks for "changed at or after the previous query's
  `asOf`" then never misses a change. (Strengthened during T044: a bound taken from items read
  after the query, or from the clock, can skip a change committed in between.)

**Queries (US3)**

- **FR-010**: The simulator MUST answer queries in a documented subset of WIQL: selecting work
  items with conditions on type, state, area path (equals and under), any field's value (equals,
  not equals, in), changed date (comparisons), ids (in), combined with and/or and parentheses,
  ordered by changed date or id; and work item link queries for parent and child.
- **FR-011**: A query MUST return the matching ids (and, for link queries, the source and target
  pairs) as ADO does; a query outside the subset MUST be refused with a reason naming the
  unsupported construct.

**Relations (US4)**

- **FR-012**: The simulator MUST support parent/child (hierarchy) and predecessor/successor
  (dependency) links, added and removed through a patch, shown on both items, and recorded in the
  history of both. As ADO (confirmed in T001): the item the patch was sent to gets a new revision
  and update; the other item gets an update carrying the relation change but no new revision (its
  `rev` and changed date stay as they were). A link change is atomic: both records are written, or
  neither is.
- **FR-013**: The simulator MUST refuse a second parent, a hierarchy cycle, a self-link and a link
  to a missing item.

**Comments (US5)**

- **FR-014**: The simulator MUST add comments to a work item with author and time, and list an
  item's comments in either order, paged, as ADO does.

**Identities and access (US6)**

- **FR-015**: Every API request MUST be authenticated with a personal access token belonging to a
  known, active identity; others are refused as unauthenticated, and the refusal never reveals
  whether an identity exists (the same status and empty body for a missing, unknown, revoked or
  wrong token). Tokens are issued and revoked only by an operator command, run by whoever operates
  the simulator's host or container (no API issues tokens); a token is shown once when issued and
  stored only as a hash keyed by a server secret of at least 32 characters. Tokens do not expire
  in the MVP; they stay valid until revoked. Changing the server secret invalidates every token.
- **FR-016**: The simulator MUST list identities and resolve one by unique name, returning id,
  display name and unique name; it MUST record the authenticated identity as the changer of every
  change and the author of every comment.
- **FR-017**: Tokens MUST never appear in responses (other than the operator command that issues
  one), logs, the seed file or the contract fixtures; reading the data store does not reveal
  them.

**Project, area paths and process (US7)**

- **FR-018**: The simulator MUST be seeded from a seed file describing one organisation and
  project, its area path tree, the work item types with their allowed states and fields (following
  the ADO Agile process, with the Epic's states being the terminal stages), and the identities; it
  MUST serve the area path tree and the types, states and fields.
- **FR-019**: A reset MUST return the simulator to the seeded content only when explicitly
  confirmed; all data MUST survive a restart.

**Contract (US8)**

- **FR-020**: The simulator MUST publish a machine-readable description of every supported
  operation (paths, parameters, bodies, responses, refusals) and serve exactly those operations;
  every other ADO operation is refused as not found or not supported.
- **FR-021**: The repository MUST hold contract fixtures (request and expected response for every
  operation, including conflict, validation, unauthenticated and unsupported refusals) that pass
  against a freshly seeded simulator, and a list of known differences from real ADO.
- **FR-022**: Paths, field reference names, patch format, error shape and status codes MUST follow
  the ADO REST API (version 7.1) for the operations in the subset, as given by Microsoft's
  published REST API reference; the contract tests check the simulator against that subset, and
  any unavoidable difference MUST be listed with the contract.

- **FR-025**: Every ADO operation MUST require `api-version`; a missing or unsupported version is
  refused with `400` naming the supported versions (`7.1`, and `7.1-preview.4` for comments).
- **FR-026**: Requests MUST be bounded: a field value or comment over 1 MB, a patch over 500
  operations, a query over 32 KB or a request body over 5 MB is refused with `400` before anything
  is stored.

**Separation and operation**

- **FR-023**: The simulator MUST run as its own process with its own data store and import nothing
  from the platform's code; it MUST NOT read the platform's specs, settings or data.
- **FR-024**: The simulator MUST answer a health check and serve its contract description without
  authentication; every other operation needs a token (FR-015). It MUST log each request's
  operation, identity and outcome, and no log line (including errors) may contain a field value,
  comment text or token.

### Key Entities

- **Organisation and project**: the one seeded organisation and project every item belongs to.
- **Area path (classification node)**: a node in the project's area tree; every item has one.
- **Process definition**: the work item types, each with its allowed states and fields (system and
  `Custom.*`), from the seed file: the Agile process, with the Epic's states being the terminal
  stages.
- **Work item**: id, type, current revision and current field values.
- **Revision**: the work item's full field values and relations as of one revision.
- **Update**: one change: revision, changed fields (old and new values), relation changes, changer
  and time; append-only.
- **Relation**: a typed link (hierarchy or dependency) between two work items.
- **Comment**: text on a work item with author and time.
- **Identity**: a demo user or the service account: id, display name, unique name, active flag.
- **Access token**: a personal access token belonging to one identity, issued and revoked by an
  operator command, stored only as a hash.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every contract fixture (one per operation and refusal) passes against a freshly
  seeded simulator, and the published description lists exactly the operations served.
- **SC-002**: In a test that makes 1,000 changes to 50 items as several identities while a reader
  polls with "changed since last read", the reader sees 100% of the changes, each exactly once, in
  revision order per item, with the right changer.
- **SC-003**: In a test with 20 concurrent conditional updates of the same item at the same
  revision, exactly one succeeds and every other is refused as a conflict; no update is lost or
  half-applied.
- **SC-004**: With 5,000 work items seeded, 95% of single-item reads, updates and supported
  queries complete within 1 second, measured by the test suite on the CI or test machine and
  reported with each run.
- **SC-005**: After a restart, 100% of work items, revisions, relations and comments are unchanged.
- **SC-006**: Seeding or resetting the demo board from the seed file takes under 1 minute.
- **SC-007**: No token appears in any response, log line, seed file or fixture, apart from the
  issuing command's one-time output (checked by a scan in the tests).
- **SC-008**: The simulator's code imports nothing from the platform, and the platform's code
  imports nothing from the simulator (checked by a boundary test).

## Assumptions

- One organisation and one project for the MVP; area paths, not iterations, organise the board.
- The process definition is the simulator's own seed file (the Agile process's types and states,
  the Epic's terminal-stage states and the custom fields features 016–018 need); which types and
  fields the platform uses is decided by the tracker mapping in feature 016, not here. The seed's
  terminal stages are data, never code.
- The board's columns are the Epic's states (as ADO boards map columns to states); the rule that
  only the platform changes them belongs to features 016 and 017.
- Access control is identity only: any authenticated identity may read and change any item in the
  project. Who may make which decision is checked by the platform (SA §22.3), never by the
  simulator.
- Threat model for the MVP: the simulator runs on the demo host for a few known people and the
  platform's service account, reachable on the platform network and one published port; it holds
  synthetic data only (SA C-2). The accepted risk is that any token holder can change any item;
  the platform treats every board change as a request and checks it (SA §22.3).
- Text and HTML stored in fields and comments are untrusted: features 017 and 018 must never
  render them as markup (as the platform's UI rule, 007 FR-013).
- Deleting work items, attachments, iterations, saved queries, webhooks (service hooks) and the
  boards configuration API are out of scope; webhooks may be added later as a faster path, with
  polling kept (SA §22.3).
- ADO API version 7.1 is the reference for paths and shapes; any deliberate difference is listed
  with the contract (FR-022).
- The simulator's UI (board, backlog, form) is features 017 and 018; the platform's adapter, sync
  and mapping are feature 016.
