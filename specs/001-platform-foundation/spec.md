# Feature Specification: Platform Foundation

**Feature Branch**: `001-platform-foundation`

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description: "Feature 001 platform-foundation. Build the platform foundation of the Agentic ADLC platform (build plan §6 row 001; SA §10 Data architecture, §15 Deployment and infrastructure, §11 identity and secrets, Annex A.6 naming): one-command environment, versioned schema changes over four owned data areas with an immutable ledger area, environment-only configuration, local sign-in mapped to catalogue roles behind a replaceable identity interface, a trace collector, shared developer/CI checks and per-service health checks."

**Source sections**: SA §10, §11, §15, Annex A.6; build plan §5, §6 (row 001), §9; constitution I, II, VII, VIII, IX, XI, XII, XIII.

## Clarifications

### Session 2026-11-09

- Q: Should ledger records be impossible to update or delete for every data store identity, including the schema owner, rather than only for the application identity? → A: Block every identity; only reset and full rollback remove ledger data, by removing the whole table through the schema-owner identity after confirmation.
- Q: How are demo sign-in credentials set for local accounts? → A: Each account has its own credential, stored only as a salted hash in a per-environment account file kept outside the repository; a helper command produces the hash; the repository ships only an example account file with placeholders.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One-command platform environment (Priority: P1)

A platform engineer (or the person running the demo) brings the whole platform up on a laptop
or the single demo host with one command, sees every service report healthy, and can stop it,
or reset all of its data to an empty state, with one more command each. Every developer and the
demo host run the same environment definition.

**Why this priority**: every later feature (002–014) builds and tests inside this environment;
without it nothing else can be run or demonstrated (SA C-5, §15).

**Independent Test**: from a clean checkout with only the documented prerequisites installed,
run the start command and confirm that the data store, the trace viewer and the platform API
all report healthy; run the reset command and confirm that all platform data is gone.

**Acceptance Scenarios**:

1. **Given** a clean checkout and a filled-in local settings file, **When** the engineer runs
   the start command, **Then** the data store, the trace viewer and the platform API start and
   each reports healthy within 3 minutes.
2. **Given** a running environment, **When** the engineer runs the stop command and then the
   start command again, **Then** previously stored data is still present (state survives
   restart, NFR-02).
3. **Given** a running environment with data, **When** the engineer runs the reset command and
   confirms, **Then** all platform data is removed and the schema is re-created empty.
4. **Given** one service fails to start, **When** the engineer checks status, **Then** that
   service is shown as unhealthy by name and the others are shown with their own state.

---

### User Story 2 - Versioned schema changes over four owned data areas (Priority: P1)

A platform engineer applies and rolls back database schema changes as numbered, repeatable
migrations. The platform's data is split into four separately owned areas, `spec`, `run`,
`ledger` and `events` (SA §10), and the ledger area cannot be altered after a record is written.

**Why this priority**: every later feature adds tables through this mechanism, and the ledger
immutability rule (constitution V) must hold from the first record ever written.

**Independent Test**: against an empty data store, apply all migrations and confirm the four
areas exist; insert a ledger record as the application identity and confirm update and delete
are refused; roll back all migrations and confirm the store is empty again.

**Acceptance Scenarios**:

1. **Given** an empty data store, **When** migrations are applied, **Then** the four areas
   `spec`, `run`, `ledger` and `events` exist with their baseline tables, and the current
   migration version is recorded.
2. **Given** a migrated store, **When** migrations are rolled back to the beginning, **Then**
   the four areas and their tables no longer exist.
3. **Given** a record in the ledger area, **When** the application identity or the
   schema-owner identity tries to update or delete it, **Then** the data store refuses the
   change and the record is unchanged.
4. **Given** a record in the ledger area, **When** the application identity inserts a new
   record, **Then** the insert succeeds (append-only, not read-only).
5. **Given** the migrations have already been applied, **When** they are applied again,
   **Then** nothing changes and no error is raised.

---

### User Story 3 - Configuration and secrets from the environment only (Priority: P1)

A platform engineer configures every service through environment settings. The repository
holds a documented example settings file with placeholder values only; real secrets never enter
the repository. A missing or invalid required setting stops startup with a message naming the
setting.

**Why this priority**: constitution XI (no secrets in code, specs, prompts or logs) must hold
from the first commit; a silent misconfiguration on the demo host would waste rehearsal time.

**Independent Test**: start the platform API with one required setting removed and confirm it
exits with a message naming that setting; scan the repository and confirm no secret values are
present.

**Acceptance Scenarios**:

1. **Given** a required setting is missing, **When** the platform API starts, **Then** it
   stops before serving requests and the message names the missing setting.
2. **Given** a setting has an invalid value (e.g. text where a number is expected), **When**
   the platform API starts, **Then** it stops and the message names the setting and the
   expected form, without printing the value of any secret setting.
3. **Given** the repository, **When** the secret scan runs as part of the shared checks,
   **Then** it finds no secrets and the example settings file contains only placeholders.
4. **Given** the platform is running, **When** its logs are inspected, **Then** no secret
   setting value appears in them.

---

### User Story 4 - Local sign-in mapped to catalogue roles (Priority: P2)

A demo participant (business owner, terminal owner, CoE member) signs in with a local account.
The platform then knows who they are and which roles from the role catalogue (TDS §3) they
hold. Sign-in goes through an identity interface that a standard OIDC provider can replace
later without changes to the rest of the platform (SA §11, constitution VII).

**Why this priority**: the human inbox (007) and every sign-off need a known person and role;
it is P2 because features 002–006 can be built and tested before anyone signs in.

**Independent Test**: sign in with a configured local account and confirm the platform returns
the person's identity and roles; sign in with an unknown account or wrong password and confirm
it is refused.

**Acceptance Scenarios**:

1. **Given** a configured local account with roles `business_owner` and `product_owner`,
   **When** the person signs in with correct credentials, **Then** the platform identifies the
   person and reports both roles.
2. **Given** an unknown account name or a wrong password, **When** sign-in is attempted,
   **Then** it is refused with the same generic message in both cases, and the attempt is
   logged without the password.
3. **Given** a local account configured with a role that is not in the role catalogue,
   **When** the platform starts, **Then** startup stops with a message naming the account and
   the unknown role.
4. **Given** a signed-in person, **When** they call a protected endpoint without a valid
   session, or after the session has expired, **Then** the request is refused (deny by
   default).

---

### User Story 5 - Shared checks for developers and CI (Priority: P2)

A pull-request reviewer relies on every change having passed the same checks that developers
run locally, through one set of named commands: lint, type check, unit tests, migrations
applied on a clean data store, and secret scan. CI calls exactly those commands, and the build
fails if any of them fails.

**Why this priority**: constitution IX requires every feature to pass CI before merge; the
checks must exist before the first platform code beyond this feature is written.

**Independent Test**: run the shared check command locally on the initial codebase and see it
pass; introduce a deliberate type error and see the same command, and the CI workflow, fail.

**Acceptance Scenarios**:

1. **Given** the initial codebase, **When** the shared check command runs, **Then** lint,
   type check, unit tests, migration check and secret scan all pass.
2. **Given** a change that breaks any single check, **When** the shared check command runs
   locally or in CI, **Then** the run fails and names the failing check.
3. **Given** the CI workflow definition, **When** it is inspected, **Then** it calls the same
   named commands developers use, and no check exists only in CI.

---

### User Story 6 - Trace collector ready for later features (Priority: P3)

A platform engineer has a trace collector and viewer running in the environment, and the
platform API sends its own request traces to it, so later features can tag agent and tool
calls with `run_id` and see them in one place (constitution X).

**Why this priority**: no run exists yet in this feature, but features 003–006 rely on the
collector being there; it is cheap to add now and costly to retrofit.

**Independent Test**: start the environment, make one request to the platform API, and find
that request's trace in the trace viewer.

**Acceptance Scenarios**:

1. **Given** a running environment, **When** a request is made to the platform API, **Then**
   a trace for that request appears in the trace viewer within 30 seconds.
2. **Given** the trace collector is down, **When** the platform API handles requests, **Then**
   requests still succeed (tracing failure never blocks the platform) and a warning is logged.

---

### Edge Cases

- The start command is run while the environment is already running: it reports the current
  state and does not create duplicates or lose data.
- The data store is not yet ready when the platform API starts: the API waits up to a
  configured limit, then exits with a clear message; it does not report healthy early.
- Migrations are run against a store that is ahead of the code (newer migration recorded than
  the code knows): the command stops and reports the version mismatch.
- A rollback is attempted on a store that holds ledger records: rollback is a development and
  reset operation only; it removes the ledger table as a whole through the schema-owner
  identity after confirmation, never edits individual records, and is never available to the
  application identity.
- The reset command is run on the demo host by mistake: it requires explicit confirmation and
  states which environment it is about to wipe.
- A required port is already in use on the host: start fails with a message naming the
  service and the port.
- Two local accounts share the same name: startup stops and names the duplicate.
- The `demo` environment is started with an account that still has the example placeholder
  credential: startup stops and names the account.

## Requirements *(mandatory)*

### Functional Requirements

**Environment**

- **FR-001**: The platform MUST be startable, stoppable and resettable with one documented
  command each, using a single environment definition shared by development and the demo host.
- **FR-002**: The environment MUST include, as separate services, the data store, a trace
  collector with viewer, and the platform API; later features add their services to the same
  definition.
- **FR-003**: Every platform service MUST expose a health check, and a status command MUST
  show each service's health by name.
- **FR-004**: Stored data MUST survive a stop and start of the environment; only the reset
  command removes it, after explicit confirmation naming the target environment.
- **FR-005**: The environment MUST distinguish at least two named environments, `dev` and
  `demo` (SA §15), selected by configuration only.

**Data store and migrations**

- **FR-006**: The data store MUST be organised into four separately owned areas named `spec`,
  `run`, `ledger` and `events` (SA §10; Annex A.6: one lowercase word each).
- **FR-007**: Schema changes MUST be applied as ordered, versioned migrations that can be
  applied forward and rolled back step by step, and the applied version MUST be recorded in the
  store.
- **FR-008**: Applying migrations that are already applied MUST be a no-op.
- **FR-009**: This feature's migrations MUST create only the four areas and the minimum
  baseline tables needed to prove the migration path and the ledger rule: one append-only
  ledger record table in `ledger` holding a record key, a content hash, the previous record's
  hash and a written-at timestamp. Full runtime, spec-registry and event tables belong to
  features 002, 003 and 005.
- **FR-010**: The platform MUST use two distinct data store identities: a schema-owner identity
  used only by migrations, and an application identity used by running services.
- **FR-011**: The application identity MUST be able to insert and read ledger records. Every
  data store identity, including the schema owner, MUST be refused on any update or delete of
  an individual ledger record, enforced by the data store itself, not by application code
  (constitution V; SA §10 immutability, §11 "no update rights for any role"). Ledger data can
  only be removed as a whole table, by reset or full rollback through the schema-owner
  identity after explicit confirmation.
- **FR-012**: All database object names MUST follow SA Annex A.6 (singular `snake_case`
  tables, `<event>_at` timestamps, `<entity>_id` foreign keys).

**Configuration and secrets**

- **FR-013**: All configuration and secrets MUST come from environment settings; the
  repository MUST contain a documented example settings file with placeholder values only.
- **FR-014**: Each service MUST validate its settings at startup and stop before serving
  requests if a required setting is missing or invalid, with a message naming the setting and
  the expected form.
- **FR-015**: Secret settings MUST never be printed in logs, error messages, traces or health
  output.
- **FR-016**: The shared checks MUST include a secret scan of the repository that fails the
  build if a secret is found.

**Identity**

- **FR-017**: People MUST sign in through an identity interface whose contract (sign in,
  identify current person, list their roles, sign out) is the same for local accounts and for
  a standard OIDC provider, so replacing local accounts changes configuration and one adapter,
  not callers (constitution VII; SA §11).
- **FR-018**: For the MVP, local accounts MUST be defined in a per-environment account file
  kept outside the repository (account name, display name, one or more roles, and a
  per-account credential stored only as a salted hash). A helper command MUST turn a
  credential entered by the operator into that hash without echoing or storing the plain
  credential. The repository MUST ship only an example account file with placeholder hashes;
  the platform MUST refuse to start in `demo` if any account still has a placeholder.
- **FR-019**: Roles assigned to accounts MUST be names from the role catalogue (TDS §3); role
  names MUST NOT be hard-coded in platform code (constitution I) but read from the catalogue
  file in `adlc-specs/shared/`.
- **FR-020**: Unknown accounts and wrong credentials MUST be refused with the same generic
  message; every sign-in attempt, successful or not, MUST be logged with account name and
  time, never the credential.
- **FR-021**: All platform API endpoints other than health checks and sign-in MUST require a
  valid signed-in session (deny by default, constitution XI); sessions MUST expire after a
  configured period.

**Shared checks and CI**

- **FR-022**: One set of named commands MUST run lint, strict type check, unit tests, a
  migration check (apply all, roll back all, apply all on a clean store) and the secret scan;
  one aggregate command MUST run them all.
- **FR-023**: CI MUST invoke exactly those named commands on every pull request and on the
  main branch, and fail if any fails; no check may exist only in CI.
- **FR-024**: The shared checks MUST pass on the initial codebase delivered by this feature.

**Tracing**

- **FR-025**: The platform API MUST send a trace for each request it handles to the trace
  collector, using a vendor-neutral trace format so the collector can be replaced by
  configuration (constitution VII, X).
- **FR-026**: Tracing failure MUST NOT fail or delay requests beyond normal handling; it MUST
  be logged as a warning.

**Repository layout**

- **FR-027**: The repository MUST follow the layout in build plan §5: `src/adlc/` with one
  module per layer (`spec_toolkit`, `orchestration`, `policy`, `ledger`, `agents`, `api`, `ui`),
  `adlc-specs/` (with `terminals/`, `shared/`, `playbooks/`, `checklists/`, `schema/`),
  `mcp_servers/`, `pilot/`, `db/migrations/`, `tests/` (`unit/`, `integration/`, `scenario/`),
  `deploy/` and `.github/workflows/`. Modules for later features MAY be empty placeholders with
  a README stating which feature fills them.
- **FR-028**: This feature MUST NOT add terminal-specific or use-case-specific values anywhere
  (constitution I, II); the role catalogue file is the only lifecycle catalogue it adds, and
  its full validation is delivered by feature 002.

### Key Entities

- **Environment**: a named deployment of the platform (`dev`, `demo`) defined by one
  environment definition plus its settings; holds the list of services and their health.
- **Service**: one running part of the platform (data store, trace collector, platform API,
  and later ones); has a name, a health state and required settings.
- **Setting**: a named configuration value supplied by the environment; required or optional;
  secret or not; has an expected form.
- **Data area**: one of `spec`, `run`, `ledger`, `events`; has an owner concern and access
  rules for the schema-owner and application identities.
- **Migration**: an ordered, versioned schema change with a forward and a backward step; the
  store records which version is applied.
- **Ledger record (baseline)**: an append-only entry with record key, content hash, previous
  record hash and written-at time; extended by feature 005.
- **Local account**: a person who can sign in; account name (unique), display name, roles
  from the role catalogue, own salted-hash credential; defined in the environment's account
  file, never in the repository.
- **Role**: an entry in the role catalogue (TDS §3), e.g. `business_owner`, `adlc_coe`.
- **Session**: proof that a person signed in; tied to one account; expires.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new developer goes from a clean checkout to a healthy running platform in
  under 15 minutes by following the README, using one start command.
- **SC-002**: After the start command, all services report healthy within 3 minutes on the
  demo host.
- **SC-003**: Migrations apply to an empty store and roll back to empty with zero errors in
  10 out of 10 consecutive runs.
- **SC-004**: 100% of attempts by any data store identity (application or schema owner) to
  update or delete a ledger record are refused by the data store.
- **SC-005**: For every required setting, removing it causes startup to stop with a message
  that names that setting (verified for each required setting).
- **SC-006**: A configured local user can sign in and see their roles in under 10 seconds;
  100% of sign-ins with unknown accounts or wrong credentials are refused.
- **SC-007**: The full shared check command completes in under 10 minutes and gives the same
  result locally and in CI for the same commit.
- **SC-008**: Zero secrets are found in the repository by the secret scan, and zero secret
  values appear in logs during a full start, sign-in and stop cycle.
- **SC-009**: A request to the platform API appears in the trace viewer within 30 seconds.

## Assumptions

- **Identity for MVP is local accounts** (user decision, 2026-11-09; build plan §10 fallback);
  a standard OIDC provider is a later, configuration-plus-adapter change.
- **Trace viewer for MVP is a lightweight vendor-neutral one** (user decision, 2026-11-09;
  build plan §4 fallback); the heavier agent-tracing stack can be added later behind the same
  trace format.
- The role catalogue file holds the 15 roles of TDS §3 and is created in this feature as data
  only; schema validation of catalogues arrives in feature 002.
- A person may hold several roles (in the demo, one person may act as several owners).
- Default session lifetime is 8 hours; the value is a setting.
- Reset and full rollback are development and demo-preparation operations; they need explicit
  confirmation and use the schema-owner identity.
- The demo host is a single machine able to run containers (SA C-5, §15); its hosting target
  (ADR-07) is undecided and does not affect this feature.
- The object store for artifacts is not part of this feature; it arrives with the ledger in
  feature 005.
- Email notifications (SA §8.2) are out of scope here; they arrive with the human inbox (007).
- CI runs on the Git host's CI service; until a remote exists, developers run the same
  commands locally.
