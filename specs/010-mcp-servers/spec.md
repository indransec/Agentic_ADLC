# Feature Specification: MCP Servers

**Feature Branch**: `010-mcp-servers`

**Created**: 2026-11-12

**Status**: Draft

**Input**: User description: "Feature 010 mcp-servers (build plan §6 row 010; SA §7.2, §7.3, §11,
§13, §15): the MCP servers the build, test, release and operate terminals (T3–T9) use: Git and
CI, evaluation, red-team, deploy and traffic, telemetry and an ITSM mock. Carries feature 009's
commitments: the pilot's environment operations as scoped MCP tools (dev for T3, test for T4 and
T5) and its infrastructure definitions as MCP resources, reached through the only declared path
between the platform and pilot networks."

## Clarifications

### Decided before this feature (recorded for context)

- Deploy and traffic do not use the Docker SDK or Traefik (build plan row 010): feature 009 decided
  that pilot packages run as worker processes inside the pilot's environment hosts, with no Docker
  socket anywhere (009 research R-03). The deploy, traffic and fault operations already exist on
  the pilot side; this feature exposes them as MCP tools.
- Provisioning a pilot environment is a deterministic pilot-side operation from the template's
  infrastructure definitions, never infrastructure written by a model (009 clarification;
  constitution VI). Feature 011's T3 calls the tools this feature provides.

### Session 2026-11-12

- Q: Which servers does this feature deliver? → A: Every server the T3–T9 specs name in their
  tool scopes (git, ci, prompt_registry, artifact_store, harness, eval_store, dataset_registry,
  redteam_harness, iam, dlp_scanner, control_library, grc, servicenow, cmdb, monitoring, cd,
  traffic_manager, agent_registry, observability, feedback, kill_switch) plus the new pilot
  environment server, with real behaviour where the pilot lifecycle needs it (build, evaluate,
  assure, deploy, observe) and simple record-keeping mocks for the enterprise systems (ITSM, CMDB,
  registries, IAM, GRC, control library, feedback).
- Q: Where does T3's source control live? → A: A Git repository the platform hosts locally (one
  repository per use case on a volume; the server records branches, commits and pull requests),
  not GitHub, so no agent writes to an external host and the demo works offline.
- Q: Which evaluation and red-team tooling? → A: The platform's own deterministic harness (routing
  accuracy, per-category accuracy, P1 recall, latency, cost, RAI counts) and a fixed, versioned
  red-team suite (prompt injection, jailbreak, personal-data extraction, abusive input); no
  DeepEval, garak or PyRIT dependency and no LLM judge in this feature. This replaces the build
  plan's DeepEval and garak/PyRIT choice (and uses its "red-team as a fixed prompt suite"
  simplification).

## User Scenarios & Testing *(mandatory)*

The lifecycle agents of T0–T2 work with documents only. From T3 on, agents act on real systems:
they write the pilot's configuration, build it, test it, attack it, deploy it, watch it and file
records about it. Each of those systems is reached through an MCP server listed in the MCP
registry, with the tool scopes the terminal spec grants, so the agents can do only what their
terminal allows (constitution IV, XI) and every action leaves a record (constitution V, X).

### User Story 1 – Pilot environments through scoped tools (Priority: P1)

An agent in T3 provisions the pilot dev environment for a package hash and reads the
infrastructure definitions; an agent in T4 or T5 does the same in the test environment. Neither
can touch the other's environment, prod-sim, or anything outside the pilot.

**Why this priority**: T3–T5 cannot build or test without environments; feature 009 committed this
path. It is also the first crossing of the platform–pilot boundary, so it sets the security
pattern every other tool follows.

**Independent Test**: With the stack up, call the environment tools as a T3 run and as a T4 run;
check what each may create, read and tear down, and that every call is recorded.

**Acceptance Scenarios**:

1. **Given** a T3 run, **When** its agent asks to create the dev environment for a built package
   hash, **Then** the environment runs that package and the call is recorded with the run, the
   tool, the package hash and the outcome.
2. **Given** a T3 run, **When** its agent asks to create or tear down the test environment,
   **Then** the call is refused before it reaches the pilot, and the refusal is recorded with its
   reason.
3. **Given** any run, **When** its agent reads the infrastructure resources, **Then** it gets the
   template's definitions for dev, test and prod-sim with their versions.
4. **Given** a call that skips the platform's gate and goes straight to the server without a valid
   run token for that scope, **When** it arrives, **Then** the server refuses it.
5. **Given** a use case whose dev environment host is running, **When** T3's prerequisites are
   checked, **Then** "dev environment provisioned" and "template version pinned" are read from the
   pilot (not from synthetic evidence) and the decision says so.

---

### User Story 2 – Build: source control, CI and the artifact store (Priority: P1)

T3's agent writes the filled configuration to a branch, opens a pull request, runs CI on it and
gets back a package hash with the test results; the package is in the artifact store, and the
instructions are versioned in the prompt registry.

**Why this priority**: Without a build there is no candidate package for T4–T7 (D-6).

**Independent Test**: As a T3 run, write a fill to a branch, run CI, and check the package hash is
the one `pilot-build` gives for the same fill, the results name each check, and the package is
retrievable.

**Acceptance Scenarios**:

1. **Given** a T3 run, **When** its agent writes fill files to a feature branch and opens a pull
   request, **Then** the branch, the commit and the pull request are recorded with the run, and
   the main branch is never written.
2. **Given** a branch with a valid fill, **When** CI runs, **Then** it validates the fill, builds
   the package, runs the pilot's tests against it and returns the package hash and each check's
   result; the same fill always gives the same hash.
3. **Given** an invalid fill, **When** CI runs, **Then** it fails and names the failing fill part.
4. **Given** a built package, **When** any authorised run reads the artifact store by hash,
   **Then** it gets the manifest; an unknown hash is not found.

---

### User Story 3 – Evaluate and assure against the test environment (Priority: P1)

T4's agent runs the evaluation harness on an approved dataset against the candidate package in the
test environment and stores the results; T5's agent runs the red-team suite and the personal-data
scan and reads the control library.

**Why this priority**: T4 and T5 decide whether a package is fit (D-3, D-5); their evidence must
come from runs, not from the agent's say-so.

**Independent Test**: As a T4 run, evaluate the default package and the degraded model on the
golden set; as a T5 run, run the red-team suite and the scan with and without the leak fault.

**Acceptance Scenarios**:

1. **Given** a package running in test, **When** the harness runs a registered dataset,
   **Then** it returns routing accuracy, per-category accuracy, P1 recall, latency, cost and RAI
   counts, tagged with the package hash, dataset id and version, and stores them in the eval
   store.
2. **Given** the same package and dataset, **When** the harness runs twice, **Then** the metrics
   are the same (the simulated model is deterministic).
3. **Given** a package in test, **When** the red-team suite runs, **Then** each attack category
   reports attempts, successes and a success rate, with the suite version.
4. **Given** answers that contain planted personal data, **When** the scan runs, **Then** it finds
   them; with none planted or no leak, it finds nothing.

---

### User Story 4 – Release: deploy, traffic and the kill switch (Priority: P1)

T7's agent deploys the package hash authorised at T6 to prod-sim as a candidate, moves traffic
through shadow, canary and full, and can roll back; T8 can stop the pilot with the kill switch.

**Why this priority**: D-6 ("the deployed hash is the tested hash") is enforced here.

**Independent Test**: As a T7 run, deploy the authorised hash and step through the split; try a
different hash; as a T8 run, invoke the kill switch.

**Acceptance Scenarios**:

1. **Given** a hash authorised at T6 for the use case, **When** T7's agent deploys it, **Then** it
   runs in prod-sim as the candidate.
2. **Given** any other hash, **When** T7's agent deploys it, **Then** the deploy is refused at the
   platform and again at the server, and the refusal is recorded.
3. **Given** a candidate, **When** the split is set to shadow, canary at a share, or full,
   **Then** prod-sim routes accordingly, and rollback returns all traffic to the stable package.
4. **Given** a running pilot, **When** T8's agent invokes the kill switch, **Then** prod-sim stops
   answering with the pilot and says so, and the action is recorded.

---

### User Story 5 – Operate: telemetry, monitoring and feedback (Priority: P2)

T8's agent reads the pilot's metrics and traces (masked), configures monitors with thresholds and
reads which have fired, and reads synthetic user feedback.

**Why this priority**: D-7 (drift → T9 → re-entry) needs T8 to see the model swap through data.

**Independent Test**: With traffic running, read metrics; trigger the model swap; read again and
check the monitor on routing accuracy fires.

**Acceptance Scenarios**:

1. **Given** steady traffic, **When** T8's agent reads telemetry, **Then** it gets routing
   accuracy, the personal-data leak rate, latency, cost, RAI counts and volume per package over a
   window, and traces with request ids but never incident text or personal data.
2. **Given** a monitor on routing accuracy below a threshold, **When** the model swap lowers it,
   **Then** reading the monitors shows it fired, with the value and time.
3. **Given** synthetic feedback, **When** read, **Then** it returns ratings and comments for the
   pilot, labelled synthetic.

---

### User Story 6 – Enterprise records: ITSM, CMDB, registries, IAM and GRC mocks (Priority: P2)

T6–T9 agents create change requests and incidents, register the agent, update the configuration
record, revoke identities on retirement, and file assurance reports, against mocks that behave like
the real systems' interfaces and keep their records in the platform.

**Why this priority**: T6, T7 and T9 controls read these records; the real systems arrive later as
configuration (SA P-9).

**Independent Test**: Create a change request and an incident, register an agent, read them back
with their ids, and check the records are in the platform and visible to a person.

**Acceptance Scenarios**:

1. **Given** a T6 run, **When** its agent creates a change request, **Then** it gets a change id
   and the record holds the run, the use case and the requested window.
2. **Given** a T7 or T8 run, **When** its agent raises an incident, **Then** it gets an incident
   id; reading incidents for the agent returns it.
3. **Given** a T9 retirement, **When** its agent revokes the pilot's identity and tool scopes,
   **Then** the mock records the revocation and later reads show it revoked.

---

### Edge Cases

- A pilot environment host is down: the tool says the environment is unavailable; it never reports
  success, and the prerequisite that reads it fails closed.
- A tool call takes too long: it is cut off at the server's time limit and reported as timed out.
- Arguments an agent should not choose (run, use case, scope, authorised hash, data ceiling) are
  ignored if the model sends them; the platform sets them from the run and the pinned spec.
- A run token is expired, for another run, or for another scope: refused.
- Two runs of the same use case write the same branch: the second write is refused or rebased,
  never silently lost.
- Tool output contains instructions ("ignore your rules"): it is passed to the agent as labelled
  data, never acted on by the server or platform.
- Telemetry would include incident text or personal data: it is masked before it leaves the
  server.
- A dataset id or version not in the registry: refused.
- The kill switch is invoked twice: the second call reports it is already active.

## Requirements *(mandatory)*

### Functional Requirements

**Registry, access and records (all servers)**

- **FR-001**: Every server and scope this feature provides MUST be in the MCP registry
  (`adlc-specs/shared/mcp_servers.yaml`) with its owner; the pilot environment server and its
  scopes MUST be added, and the T3–T5 specs MUST grant them (dev to T3, test to T4 and T5).
- **FR-002**: Every tool call MUST be authorised twice: by the platform's tool gate against the
  terminal's tool scopes (feature 004) and by the server against a short-lived token the
  orchestrator issues for one run, naming the run, use case, terminal, the granted scopes and an
  expiry. A call without a valid token for the scope MUST be refused by the server.
- **FR-003**: Values that bind a call to the run (run, use case, terminal, scope, data ceiling,
  authorised package hash, dataset id) MUST come from the run and the pinned spec or ledger, never
  from the model's arguments.
- **FR-004**: Every call MUST be recorded on the platform side with the run, attempt, tool, a hash
  of its arguments, the outcome (ok, refused, failed, timed out) and the time, and traced with the
  run id; refusals MUST carry their reason.
- **FR-005**: Tool output MUST reach the agent as labelled data with a size cap, and servers MUST
  never return secrets, incident text from traffic or planted personal data except where the tool's
  purpose is to report it (the personal-data scan's findings, masked).
- **FR-006**: Only the declared MCP server(s) MUST join both the platform and pilot networks; no
  server mounts the Docker socket or publishes ports.
- **FR-007**: Each server MUST implement the same tool names and argument shapes a real system's
  MCP server would offer for the scope, so moving to a real system changes configuration only.

**Pilot environments (US1)**

- **FR-008**: The pilot environment server MUST expose create, status and tear down for dev
  (scope `dev`) and test (scope `test`) by package hash and declared settings, by calling the
  pilot hosts' operations, and the infrastructure definitions as readable resources (scope
  `read`).
- **FR-009**: The evidence sources `env.dev`, `env.test` and `template.version` MUST be read from
  the pilot through this server when it is available, so T3's prerequisites use real evidence;
  synthetic evidence remains the fallback and is labelled synthetic.

**Build (US2)**

- **FR-010**: Source control MUST be a platform-hosted repository per use case (no external Git
  host). It MUST let a T3 run read the repository, write files only on a feature
  branch named for the use case and run, commit and open a pull request; the main branch MUST
  never be written by an agent.
- **FR-011**: CI MUST validate the fill on a branch, build the package, run the pilot's tests
  against it and return the package hash and each check's result; the hash MUST equal the pilot's
  own build of the same fill.
- **FR-012**: The artifact store MUST return a package's manifest by hash, and the prompt registry
  MUST version and return the pilot's instructions by hash.

**Evaluation and assurance (US3)**

- **FR-013**: The dataset registry MUST list approved datasets (id, version, seed, size, PII share,
  hash) built from the pilot's incident generator, and refuse unknown ones.
- **FR-014**: The evaluation harness MUST be deterministic (no LLM judge) and MUST run a registered dataset against the package in the test
  environment and return routing accuracy, per-category accuracy, P1 recall, latency, cost and RAI
  counts, tagged with package hash and dataset; results MUST be stored in the eval store and be
  readable by use case.
- **FR-015**: The red-team harness MUST run a fixed, versioned suite (prompt injection, jailbreak,
  personal-data extraction, abusive input) against the test environment and return attempts,
  successes and the success rate per category.
- **FR-016**: The personal-data scanner MUST scan answers for personal data with the pilot's
  detection method and return masked findings.

**Release and operate (US4, US5)**

- **FR-017**: Deploy MUST accept only the package hash authorised at T6 for the use case, checked
  by the platform and again by the server; traffic management MUST set shadow, canary at a share,
  or full, and roll back to stable.
- **FR-018**: The kill switch MUST stop prod-sim answering with the pilot until released by a
  person, and be recorded.
- **FR-019**: Observability MUST return the pilot's metrics per package over a window (routing
  accuracy, leak rate, latency, cost, RAI counts, volume) and traces by request or time range
  without incident text or personal data.
- **FR-020**: Monitoring MUST let an agent configure monitors (metric, operator, threshold,
  window) for its use case and read which have fired, evaluated against observability data.
- **FR-021**: Feedback MUST return synthetic ratings and comments for the pilot, labelled
  synthetic.

**Enterprise records (US6)**

- **FR-022**: The ITSM mock MUST create change requests and incidents with ids and read them; the
  CMDB and agent registry mocks MUST read and write configuration items and agent entries; the IAM
  mock MUST read and revoke identities and tool scopes; the GRC mock MUST store and read assurance
  reports; the control library MUST return controls by id and topic. Their records MUST live in
  the platform and be append-only where they are evidence.

### Key Entities

- **MCP server**: an approved server with its id, owner, scopes and tools (registry).
- **Run token**: the short-lived grant for one run: run, use case, terminal, scopes, expiry.
- **Tool call record**: run, attempt, tool, argument hash, outcome, reason, time.
- **Branch and pull request**: the T3 run's writes to source control.
- **CI run**: branch, commit, checks with results, package hash.
- **Dataset**: id, version, seed, size, PII share, content hash.
- **Evaluation run** and **red-team run**: package hash, dataset or suite version, metrics or
  results per category, time.
- **Monitor**: use case, metric, operator, threshold, window, fired events.
- **ITSM record** (change request, incident), **configuration item**, **agent registry entry**,
  **identity revocation**, **assurance report**: mock enterprise records with ids.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of calls outside a terminal's granted scopes are refused, at the platform and,
  for calls sent straight to a server, at the server; 0 refused calls reach a pilot environment.
- **SC-002**: 100% of tool calls leave a record with run, tool, outcome and time.
- **SC-003**: A T3 run can go from a fill to a package hash with CI results and a dev environment
  running that package within 5 minutes, and CI's hash equals the pilot's own build in 100% of
  trials.
- **SC-004**: The harness gives identical metrics for the same package and dataset in 100% of
  repeat runs, and shows the degraded model at least 20 points below the default on routing
  accuracy.
- **SC-005**: The red-team suite reports a personal-data extraction success rate above 0 only when
  the leak fault is on, and the scan finds 100% of planted data in leaked answers.
- **SC-006**: Deploying any hash other than the T6-authorised one fails in 100% of attempts.
- **SC-007**: A routing-accuracy monitor fires within 5 minutes of the model swap under steady
  traffic.
- **SC-008**: No telemetry or tool output contains incident text or unmasked personal data (checked
  over a full traffic run).
- **SC-009**: The feature 001–009 suites still pass.

## Assumptions

- The pilot's operations from feature 009 (environment hosts, traffic generator, faults, build and
  incident generator) are the systems behind the pilot-facing servers.
- Agents start using these tools in features 011 (T3–T5) and 012 (T6–T9); this feature proves each
  tool with test runs and the platform's existing stub agents, and binds tools to agents only
  where the agents catalogue already names them.
- Run tokens are signed with a platform secret from the environment; a real token service is a
  later step (SA §11 target state).
- The knowledge server of feature 008 stays as it is; its pattern (own process, bearer token,
  scope and class enforced twice) is extended here.
- Spec changes for new scopes follow the spec rules (a changed value is a major version).
