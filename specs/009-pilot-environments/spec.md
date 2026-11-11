# Feature Specification: Pilot Environments

**Feature Branch**: `009-pilot-environments`

**Created**: 2026-11-11

**Status**: Draft

**Input**: User description: "Feature 009 pilot-environments (build plan §6 row 009; SA §14, §15;
demo script steps 4–10; demo moments D-6 and D-7): the pilot's golden template, synthetic data,
the pilot dev, test and prod-sim environments, a traffic generator and a fault injector, kept
separate from the platform so the platform treats the pilot exactly as any team's agent." Pilot use
case (user, 2026-11-11): a very simple **Incident Triage Assistant** that checks a raised incident
and assigns it to the required team according to its details.

## Clarifications

### Session 2026-11-11

- Q: Which use case is the pilot? → A: A very simple Incident Triage Assistant: it reads a raised
  incident and assigns it to the team that should handle it, according to the incident's details.
  It replaces the Travel Claims Assistant named in SA §14 and the demo script.
- Q: What does T3 fill in the golden template? → A: Configuration only (default accepted): the
  instructions, routing rules, tool bindings, thresholds, token budget and model settings; the
  agent code and the infrastructure definitions are fixed in the template.
- Q: How does the pilot reach a model? → A: A deterministic simulated model everywhere by default
  (no cost, reproducible, an exact model swap), with a real model (the development profile) as a
  setting for dev and test evaluation runs (default accepted).
- Q: Who provisions the build and test environments, and from what? → A: The golden template
  carries fixed, versioned infrastructure definitions per environment, parameterised only by the
  package hash and declared settings. Creating, checking and tearing down an environment is a
  deterministic operation on the pilot side, never infrastructure written by a model (constitution
  VI). Feature 010 exposes these operations as scoped MCP tools (dev for T3, test for T4 and T5)
  and the definitions as MCP resources; feature 011's T3 calls them, with any subagent support
  limited to SA §7.1.

## User Scenarios & Testing *(mandatory)*

The platform builds, tests, deploys and operates AI agents. Until now there is no agent for it to
act on. This feature provides the pilot, the **Incident Triage Assistant**, and everything around
it that the later terminals need:

- a **golden template** the build terminal (T3) fills, producing an immutable package identified
  by its content hash;
- three **environments**: dev (build), test (evaluation and assurance) and prod-sim (simulated
  production with shadow, canary and full rollout);
- **synthetic incidents** for the evaluation golden set and for live traffic;
- a **traffic generator** that keeps prod-sim busy, so operations (T8) has data;
- a **fault injector** for the demo: a model swap that degrades routing quality (drift) and a
  planted personal-data leak (safety event).

**What the pilot does.** An incident arrives (title, description, reporter, affected service,
urgency). The assistant decides the category, the priority and the resolver team, using two mocked
tools: a **service catalogue** (which team owns which service) and a **team directory** (the teams
and what they handle). It returns the assignment with a short reason. It never closes or resolves
incidents; a person can always override the assignment.

The pilot lives in its own environments. Platform agents reach it only through the MCP servers of
feature 010, never directly, so the platform treats it like any team's agent (SA §15).

Actors: the **CoE** (prepares the template, data and environments, runs the demo); the platform
terminals **T3, T4, T5, T7, T8** (they act on the pilot through feature 010's MCP servers, in
features 011 and 012); a **demo operator** (starts traffic and triggers faults).

### User Story 1 - The golden template builds into a package that runs everywhere (Priority: P1)

The CoE has a runnable Incident Triage Assistant skeleton. It declares exactly which parts T3 fills.
Built, it becomes a package with a content hash; the same package, unchanged, runs in dev, test and
prod-sim and assigns incidents.

**Why this priority**: every later terminal acts on this package; D-6 (what T4 tested is what T7
deployed) depends on one package identified by one hash.

**Independent Test**: Build the template with its default fill twice and compare hashes; run the
package in each environment and send it a synthetic incident; it returns an assignment.

**Acceptance Scenarios**:

1. **Given** the template with a fill, **When** it is built twice from the same input, **Then**
   both packages have the same content hash; a change to any filled part changes the hash.
2. **Given** a built package, **When** it is started in dev, test and prod-sim, **Then** each
   environment reports the same package hash and assigns a synthetic incident.
3. **Given** an incident about a known service, **When** the pilot triages it, **Then** it returns
   the category, priority, resolver team and a reason, its trace shows the service catalogue and
   team directory calls with the request id, and it stays within its token budget.
4. **Given** a fill that leaves a required part empty or invalid, **When** it is built, **Then**
   the build fails and says which part.

---

### User Story 2 - Build and test environments come from the template's infrastructure (Priority: P1)

The golden template includes the infrastructure of each pilot environment as fixed, versioned
definitions. For a given package hash, an operation creates a dev or test environment from these
definitions, reports its status (running package hash, health, endpoints inside the pilot network)
and tears it down. Nothing a model writes becomes infrastructure: the build terminal (T3) and the
evaluation and assurance terminals (T4, T5) only ask for an environment for a package, through
feature 010's MCP servers.

**Why this priority**: T3 must build and unit-test the pilot in dev, and T4 and T5 must evaluate
the immutable candidate in test; both need environments created the same way every time.

**Independent Test**: Create a dev and a test environment for a package hash, read their status,
send each a synthetic incident, tear them down; repeat and compare; try an unknown hash and an
undeclared setting.

**Acceptance Scenarios**:

1. **Given** a package hash, **When** a dev or test environment is created, **Then** it runs that
   package from the template's definitions, its status reports the hash and health, and it assigns
   a synthetic incident.
2. **Given** a running environment, **When** it is torn down, **Then** nothing of it remains, and
   creating it again gives an identical environment.
3. **Given** an unknown package hash or a setting the template does not declare, **When** creation
   is requested, **Then** it is refused with the reason and nothing is created.
4. **Given** the infrastructure definitions, **When** they are read, **Then** each environment's
   definition and version is available to the platform as reference material (feature 010).

---

### User Story 3 - Synthetic incidents feed evaluation and traffic (Priority: P1)

The CoE generates incidents across categories (access, hardware, software, network, security) and
priorities, with reporters (personas) and edge cases. With a fixed seed the set is reproducible
for T4's golden set; without one it feeds live traffic. Each incident carries its expected team,
category and priority, so routing quality can be measured. Planted test personal data appears only
in the scenarios that need it, and everything is labelled synthetic.

**Why this priority**: T4's evaluation and T8's monitoring both need realistic, repeatable input
with known right answers.

**Independent Test**: Generate two sets with the same seed and compare; check the mix of
categories, priorities, reporters and edge cases, the expected answers, the labels, and where
planted personal data appears.

**Acceptance Scenarios**:

1. **Given** a seed and a size, **When** incidents are generated twice, **Then** the two sets are
   identical.
2. **Given** a generated set, **When** it is inspected, **Then** it holds every category, every
   priority and each listed edge case, and every incident is labelled synthetic with its expected
   team, category and priority.
3. **Given** a set without personal-data scenarios requested, **When** it is inspected, **Then** no
   planted personal data appears in it.

---

### User Story 4 - Prod-sim serves rollouts and steady traffic (Priority: P1)

Prod-sim runs the pilot as replicas behind a traffic splitter. The deployment terminal (T7, through
feature 010) sets the split: shadow (the candidate receives a copy and its answers are not
returned), canary (a share of traffic) and full. The traffic generator sends a steady,
configurable stream of synthetic incidents, and can be paused.

**Why this priority**: demo steps 8 and 9 (canary then full rollout; T8 watching live traffic) need
it.

**Independent Test**: Deploy two packages to prod-sim, set shadow, canary at a given share, then
full; start traffic at a rate; measure the share each package served and the steady rate.

**Acceptance Scenarios**:

1. **Given** a stable and a candidate package, **When** the split is set to canary at a share,
   **Then** the candidate serves that share of requests within a tolerance, and each answer names
   the package that produced it.
2. **Given** shadow mode, **When** traffic flows, **Then** the candidate receives a copy of each
   request and its answers are recorded but never returned to the caller.
3. **Given** the traffic generator at a rate, **When** it runs for a period, **Then** the measured
   rate stays within a tolerance of the setting; pausing stops new requests.

---

### User Story 5 - Faults are injected on demand and recorded (Priority: P2)

For the demo, an operator triggers a fault: a **model swap** that measurably lowers routing
accuracy on live traffic (T8 raises a drift event, T9 classifies it, the use case re-enters at T2),
or a **planted personal-data leak** where the assistant's reason repeats the reporter's personal
data, which a personal-data check detects (a safety event for T5). Every fault is recorded with its
time, parameters and the package and replicas it affected, and can be reverted.

**Why this priority**: D-7 depends on it, but the environments are useful without it; the build
plan allows a single fault (the model swap) if time is short.

**Independent Test**: Measure routing accuracy on traffic before and after a model swap; trigger
the leak and check that answers expose planted data; revert both; read the fault record.

**Acceptance Scenarios**:

1. **Given** steady traffic, **When** the model swap is triggered, **Then** the online routing
   accuracy drops below its baseline by at least the configured margin within the configured
   window, and recovers after the swap is reverted.
2. **Given** steady traffic, **When** the leak is triggered, **Then** a share of answers contains
   planted personal data that a personal-data check detects, and none does after revert.
3. **Given** any fault, **When** it is triggered or reverted, **Then** a record holds the fault,
   its parameters, the time and what it affected.

---

### User Story 6 - The pilot is isolated from the platform (Priority: P2)

The pilot environments sit on their own network. Platform services cannot reach the pilot except
through the declared access paths (feature 010's MCP servers); the pilot cannot reach the
platform's database, API, knowledge server or secrets.

**Why this priority**: SA §15 requires it, so the platform treats the pilot as any team's agent
and a compromised pilot cannot touch the platform.

**Independent Test**: From a platform service, try to reach a pilot environment directly; from the
pilot, try to reach the platform database and API; both fail. The declared path succeeds.

**Acceptance Scenarios**:

1. **Given** the running stack, **When** a platform service connects to a pilot environment
   directly, **Then** the connection fails.
2. **Given** the running stack, **When** a pilot environment connects to the platform's database,
   API or knowledge server, **Then** the connection fails.
3. **Given** the declared access path, **When** it is used, **Then** it reaches only the declared
   pilot operations.

---

### Edge Cases

- An incident names a service the catalogue does not know: the pilot assigns the default
  first-line team and says why, instead of guessing an owner.
- An incident is security-related (data loss, suspected breach): it is always routed to the
  security team at the highest priority, whatever else it mentions.
- An incident is ambiguous or touches several services: the pilot picks one team, gives its
  reason, and marks the assignment for review.
- A package hash requested in prod-sim does not exist: the split is refused with a clear reason;
  the current split stays.
- The candidate replica fails during canary: its share is answered by the stable replicas and the
  failure is recorded.
- The traffic generator outpaces the pilot: requests that time out are counted and reported, not
  silently dropped.
- A fault is triggered twice: the second trigger is refused while the first is active.
- A model is unavailable: the pilot answers with a clear failure and the failure is counted.
- An incident with planted personal data arrives while no leak fault is active: the pilot does not
  repeat the personal data in its answer.

## Requirements *(mandatory)*

### Functional Requirements

**Golden template and package**

- **FR-001**: The golden template MUST be a runnable Incident Triage Assistant: one agent that reads
  an incident (title, description, reporter, affected service, urgency) and returns a category, a
  priority, a resolver team and a short reason, using a mocked service catalogue and a mocked team
  directory. It MUST NOT close or resolve incidents.
- **FR-002**: The template MUST declare the parts T3 fills and their rules: the instructions,
  routing rules, tool bindings, thresholds, token budget and model settings. The agent code and the
  infrastructure definitions are fixed in the template. A build MUST refuse a fill with a missing or
  invalid part and name it.
- **FR-003**: A build MUST produce an immutable package identified by a content hash computed from
  everything that determines behaviour. The same input MUST give the same hash; any change to a
  filled part MUST change it.
- **FR-004**: The same package MUST run unchanged in dev, test and prod-sim; each running instance
  MUST report its package hash.
- **FR-005**: The pilot MUST emit traces with the request id for each request and tool call, and
  metrics for latency, cost, routing outcome and the RAI metrics (toxicity, personal-data leakage,
  jailbreak attempts), and MUST enforce its own token budget per request.
- **FR-006**: The pilot MUST use a deterministic simulated model by default in every environment;
  a setting MUST switch dev and test to a real model through the development model profile. The
  model in use MUST be part of the configuration a running instance reports (the model swap fault
  changes it).

**Infrastructure and provisioning**

- **FR-018**: The golden template MUST hold the infrastructure definitions of the dev, test and
  prod-sim environments, versioned with the template and parameterised only by the package hash and
  settings the template declares.
- **FR-019**: Operations on the pilot side MUST create, report the status of and tear down a dev or
  test environment for a package hash, using only those definitions. Creation MUST refuse an
  unknown hash or an undeclared setting, and every operation MUST be recorded with its time,
  environment and package hash.
- **FR-020**: The same definitions and package hash MUST give the same environment every time; a
  torn-down environment MUST leave nothing running.
- **FR-021**: The infrastructure definitions MUST be readable as reference material, so feature 010
  can serve them as MCP resources and the operations as scoped MCP tools (dev for T3, test for T4
  and T5).

**Synthetic data**

- **FR-007**: A generator MUST produce incidents of every category (access, hardware, software,
  network, security) and priority, with reporters and edge cases (unknown service, ambiguous or
  multi-service, security-sensitive, missing details, duplicates, unsafe or out-of-scope text),
  each labelled synthetic with its expected team, category and priority.
- **FR-008**: With a seed and a size, the generator MUST produce the same set every time.
- **FR-009**: Planted test personal data MUST appear only in incidents of scenarios that request
  it, and be marked as planted.

**Environments**

- **FR-010**: Three pilot environments MUST exist: dev (build and unit test), test (evaluation and
  assurance against a candidate package) and prod-sim (rollout and live traffic).
- **FR-011**: Prod-sim MUST run packages as replicas behind a traffic splitter with three modes:
  shadow (copy to the candidate, its answers recorded but not returned), canary (a configured share
  to the candidate) and full. Every answer MUST name the package that produced it.
- **FR-012**: The split MUST be set through an operation that refuses unknown packages and records
  each change with its time.
- **FR-013**: The pilot environments MUST be on a network separate from the platform's. Platform
  services MUST NOT reach them except through declared access paths (the MCP servers of feature
  010); the pilot MUST NOT reach the platform's database, API, knowledge server or secrets.

**Traffic and faults**

- **FR-014**: A traffic generator MUST send synthetic incidents to prod-sim at a configured rate,
  report sent, answered, failed and timed-out counts, and be pausable and resumable.
- **FR-015**: A fault injector MUST offer a model swap that lowers routing accuracy and a planted
  personal-data leak that a personal-data check detects. Each fault MUST be triggerable,
  revertible, refused while already active, and recorded with its time, parameters and what it
  affected.
- **FR-016**: Online routing accuracy (answers that match the incident's expected team) MUST be
  measurable on prod-sim traffic, so that the model swap's effect is observable by T8 (feature 012)
  through feature 010's telemetry.

**Separation and configuration**

- **FR-017**: No platform code MUST depend on pilot internals; the pilot is configured by its own
  environment settings, uses synthetic data only, and holds no platform secrets.

### Key Entities

- **Golden template**: the pilot's source with its declared fill points and rules.
- **Fill**: the values T3 provides for the fill points.
- **Package**: the built, immutable pilot with its content hash.
- **Environment**: dev, test or prod-sim, with the packages it runs.
- **Split**: prod-sim's routing between a stable and a candidate package (mode and share), with its
  history.
- **Synthetic incident**: title, description, reporter, affected service, urgency, edge case,
  expected team, category and priority, synthetic label and optional planted personal data.
- **Service catalogue and team directory**: the mocked reference data the pilot looks up.
- **Traffic run**: rate, start, pause and counts.
- **Fault record**: fault type, parameters, trigger and revert times, affected packages and
  replicas.
- **Infrastructure definition**: the versioned definition of one pilot environment in the template,
  with its declared settings.
- **Environment operation record**: create, status or tear-down, with time, environment, package
  hash and outcome.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Two builds of the same fill give the same package hash in 100% of trials; any change
  to a filled part changes it.
- **SC-002**: The same package assigns a synthetic incident in each of dev, test and prod-sim, and
  each reports the same hash.
- **SC-003**: In canary mode at a 20% share, the candidate serves between 15% and 25% of 500
  requests; in shadow mode 0% of returned answers come from the candidate.
- **SC-004**: The traffic generator holds the configured rate within ±10% over 10 minutes.
- **SC-005**: With the default fill, routing accuracy on the golden set is at least 90%; after a
  model swap it falls below baseline by at least the configured margin within 5 minutes of steady
  traffic, and returns within the margin after revert.
- **SC-006**: A triggered leak exposes planted personal data in at least 10% of answers and is
  detected by the personal-data check; with no fault active, 0% of answers expose it.
- **SC-007**: Direct connections between platform services and pilot environments fail in 100% of
  attempts, in both directions.
- **SC-008**: The feature 003–008 suites still pass.
- **SC-009**: A dev or test environment for a package hash is running and answering within 2
  minutes of the request, and creating it twice from the same definitions and hash gives the same
  running package and configuration in 100% of trials.

## Assumptions

- The pilot is one agent with two mocked tools; no real ITSM, CMDB or paging system is called (the
  simulated ITSM of feature 010 is separate).
- The pilot replaces the Travel Claims Assistant named in SA §14 and the demo script; those
  documents are updated to match (the demo moments are unchanged).
- Feature 010 provides the MCP servers (deploy and traffic, telemetry, eval, red-team, git and
  CI, ITSM) that platform agents use to act on the pilot; this feature provides the operations
  those servers call and keeps them on the pilot side.
- T8's drift detection and the T9 re-entry (feature 012) are not built here; this feature makes
  the drift observable and the fault reproducible.
- Synthetic data only; no real employee or customer data enters the pilot environments.
- Follow-up dependencies: feature 010 adds an MCP server for these environment operations (scopes
  for dev and test provisioning) and catalogue entries, and T3–T5 tool scopes gain them through new
  spec versions; feature 011's T3 calls them. Subagent support in the runtime, if needed, follows
  SA §7.1 (at most two T3 subagents) in feature 011.
- The demo host runs everything; the pilot environments are containers on the same host in their
  own network.
