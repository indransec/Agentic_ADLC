# Feature Specification: Terminal Agents T6–T9

**Feature Branch**: `012-terminal-agents-t6-t9`

**Created**: 2026-11-12

**Status**: Draft

**Input**: User description: "Feature 012 terminal-agents-t6-t9 (build plan §6 row 012; SA §7, §12,
§13): T6 release readiness (mostly deterministic), T7 deployment, T8 operations with two or three
monitors, T9 change classification, re-entry and the retirement checklist. Simplify if late: T6
and T7 deterministic with a thin agent; one T8 monitor."

## Clarifications

### Decided before this feature (recorded for context)

- Tools come from feature 010 (deploy and traffic wrap prod-sim's own operations; only the hash
  authorised at T6 is deployable; the kill switch is released only by a person).
- The patterns of feature 011 apply: agents act through their terminal's tools, copied measured
  values are checked against recorded results, records people sign are never agent-written.
- The orchestrator already supports continuous terminals (T8 review periods), operational events
  (`raise_operational_event`, raised only by monitoring or agents) and re-entry routing (T9).

### Session 2026-11-12

- Q: How does T7 run the rollout stages? → A: Within one T7 run the agent deploys the authorised
  hash and steps through shadow, canary and full as the T6 rollout plan says, checking each
  stage's metrics from observability against the plan's success criteria; a breach makes it roll
  back. People authorise the release before (T6) and accept the handover after (T7 sign-off); no
  separate person approval per stage.
- Q: Where do the enterprise facts T6–T9 check come from? → A: From feature 010's mocks: T6's
  agent raises the change request; a person approves it in the ITSM mock through a small inbox
  action; `change`, `release` and `retirement` evidence are read from those records, with synthetic
  evidence as the labelled fallback.
- Q: Who raises T8's lifecycle events? → A: The platform raises them deterministically when a
  monitor fires (the monitors T6 configured); the T8 agent writes the periodic report and may
  propose an event, which a person confirms before it is raised.

## User Scenarios & Testing *(mandatory)*

After T5, the candidate is assured but not released. T6 checks that the whole evidence chain is
complete and consistent and prepares the release; T7 deploys exactly the authorised package and
hands it over; T8 operates it and turns signals into lifecycle events; T9 classifies a change and
routes it back into the lifecycle, or retires the agent. With this feature these four terminals
are real agents acting through feature 010's tools, and the release and operation of the pilot
are visible end to end (D-6, D-7).

### User Story 1 – T6 verifies the evidence chain and prepares the release (Priority: P1)

The T6 agent checks the gate evidence of T0–T5 (statuses, signatures, waivers and their expiry,
the bound package hash), raises the change request, configures the monitors the rollout and
operation need, writes the runbook, rollback strategy, rollout plan, ownership and readiness
artifacts, and names the deployment package; people authorise the release.

**Why this priority**: D-6 needs one hash bound from T3 to T7; T6 is where it is checked and fixed.

**Independent Test**: Run T6 after T5 for a use case; check the controls (statuses, waivers, hash
consistency, change approval, monitor coverage) read real records, and that the release
authorisation is the people's sign-off.

**Acceptance Scenarios**:

1. **Given** T0–T5 passed (or excepted) with one package hash, **When** T6 runs, **Then** the gate
   evidence summary lists each terminal's status, signers and open waivers with expiry, and the
   hash-consistency control passes.
2. **Given** a waiver that expires before the release date, **When** T6's controls run, **Then** the
   waiver-expiry control fails and names the waiver.
3. **Given** the change request, **When** it is not yet approved, **Then** the change control fails
   until it is approved.
4. **Given** T6 passes, **Then** the release authorisation is the people's sign-off, and the
   deployment package names exactly T3's candidate hash.

---

### User Story 2 – T7 deploys the authorised hash and hands it over (Priority: P1)

The T7 agent deploys the authorised package to prod-sim, verifies the environment configuration,
steps through the rollout stages checking each stage's metrics, runs smoke cases, registers the
agent in the agent registry and the CMDB, and records hypercare incidents; people accept the
handover.

**Why this priority**: D-6 (what T4 tested is what T7 deployed) and the demo's rollout moment.

**Independent Test**: Run T7 after T6 with steady traffic; check the deployed hash, the stage
metrics against the plan, the smoke results, the registry entry, and that a breach rolls back.

**Acceptance Scenarios**:

1. **Given** T6 passed, **When** T7 runs, **Then** prod-sim runs the authorised hash, each stage's
   metrics are recorded from observability, and `env.prod` equals T6's deployment package.
2. **Given** a stage breaches its success criteria, **When** T7 checks it, **Then** traffic rolls
   back to the stable package and the breach is recorded.
3. **Given** T7 passes, **Then** the agent registry and CMDB hold the agent's entry (owner,
   version, autonomy level) and the handover acceptance is the people's sign-off.

---

### User Story 3 – T8 operates the pilot and raises lifecycle events (Priority: P1)

Each review period, the T8 agent reads metrics, monitors, incidents, cost and feedback, writes
the operating health report, drift report, cost report, KPI scorecard and feedback themes, and
lifecycle events are raised when signals call for a change.

**Why this priority**: D-7 (a model swap shows up as drift, routed to T9).

**Independent Test**: With traffic running, trigger the model swap; check that the routing-
accuracy monitor fires, a drift event is raised, T9 opens, and T8's report shows the drop.

**Acceptance Scenarios**:

1. **Given** steady traffic, **When** a T8 review period runs, **Then** its reports carry the
   measured values from observability, monitors and feedback, checked against the recorded
   results.
2. **Given** the model swap lowers routing accuracy below the monitor threshold, **When** the
   monitor fires, **Then** a drift event is raised with the measured value and T9 opens.
3. **Given** a severity-1 incident, **When** T8 runs, **Then** it is in the incident log and the
   open-incident control fails until it is closed.

---

### User Story 4 – T9 classifies the change and re-enters the lifecycle, or retires (Priority: P1)

The T9 agent assesses the triggering change (drift, cost overrun, upstream change, a requested
change or a review), classifies it with the change classes, names the terminal to re-enter and
the revalidation plan; in retire mode it revokes identities and tool scopes, archives, and
checks that no dependent agent is left unowned.

**Why this priority**: D-7 (re-entry at T2) and the lifecycle's end.

**Independent Test**: After a drift event, run T9 and check the classification and re-entry
terminal; run a retirement and check the revocations and the retirement controls.

**Acceptance Scenarios**:

1. **Given** a drift event from a model change, **When** T9 runs, **Then** the change is at least
   moderate and the re-entry terminal is consistent with the class.
2. **Given** a retirement, **When** T9 runs in retire mode, **Then** the identity and tool scopes are
   revoked, data archived, and the retirement controls read those records.

---

### User Story 5 – Agents act only through their terminal's tools (Priority: P2)

T6 configures monitors and raises the change but cannot deploy; T7 deploys only the authorised
hash and cannot approve the change; T8 can invoke the kill switch but not release it; T9 revokes
only in retire mode.

**Independent Test**: Scripted replies asking for out-of-scope tools are refused and recorded.

### Edge Cases

- The change window has passed or not started: T7's prerequisite blocks until it is inside it.
- T6's package differs from T3's candidate: the hash control fails; nothing is deployable.
- Traffic is not running during a T7 stage: the stage metrics are "not measured" and the stage
  check fails rather than passing on no data.
- A monitor keeps firing: one event per breach episode (feature 010 monitors).
- T9 is triggered by a terminate decision: the retirement checklist runs.
- The kill switch is active during T8: the report shows it; only a person releases it.

## Requirements *(mandatory)*

### Functional Requirements

**Agents**

- **FR-001**: T6, T7, T8 and T9 MUST be model agents with versioned prompts and playbooks, bound
  to the tools their terminal's scopes allow, returning every mandatory artifact.
- **FR-002**: Records people sign (T6 release authorisation, T7 handover acceptance) MUST NOT be
  agent-written; they are the sign-offs (feature 011 rule).
- **FR-003**: Values the agents copy from tools (stage metrics, health metrics, cost, monitor
  values, registry entries) MUST be checked against the recorded results.

**T6**

- **FR-004**: T6 MUST summarise the gate evidence of T0–T5 from the records (statuses, signers,
  waivers and expiry, bound hashes), raise the change request with the release window, configure
  monitors covering T1's KPIs and T2's observability design, and name the deployment package as
  T3's candidate.

**T7**

- **FR-005**: T7 MUST deploy only the authorised hash, verify the environment configuration, step
  through the rollout plan's stages with stage metrics from observability, roll back on a breach,
  run smoke cases, and register the agent in the agent registry and CMDB.

**T8**

- **FR-006**: T8 MUST run per review period (continuous terminal) and report health, drift, cost,
  KPIs, incidents and feedback from observability, monitors, ITSM and feedback.
- **FR-007**: A monitor that fires on drift, cost or KPI shortfall MUST raise the corresponding
  lifecycle event deterministically (platform), with the measured value; an event the T8 agent
  proposes is raised only after a person confirms it.
- **FR-012**: A person in the change approver role MUST be able to approve or reject a change
  request in the ITSM mock from the inbox; the approval is recorded with the person and time.

**T9**

- **FR-008**: T9 MUST classify the change with the change classes, name the re-entry terminal
  consistent with the class, plan revalidation, record version lifecycle and lessons learned.
- **FR-009**: In retire mode T9 MUST revoke the agent's identity and tool scopes, record data
  disposal, and the retirement controls MUST read those records.

**Evidence**

- **FR-010**: The `change`, `release` and `retirement` evidence MUST be read from the ITSM, IAM and
  agent-registry mock records the tools produced, with synthetic evidence as the labelled
  fallback; `telemetry` and `env.prod` from observability and prod-sim.

**Replay**

- **FR-011**: The incident-triage reference use case MUST replay offline from T0 through T8's first
  review and a drift-driven T9, with scripted acting replies; the report shows tool calls per
  terminal.

### Key Entities

- **Change request**: ITSM record with window, risk, plan and approval status.
- **Rollout stage**: stage, traffic share, soak, success criteria, measured metrics, result.
- **Registry entry**: agent id, version, owner, autonomy level, package hash.
- **Review period** (T8): one run of the continuous terminal.
- **Lifecycle event**: drift, cost overrun, KPI shortfall, upstream change, with its evidence.
- **Retirement record**: revocations, data disposal, dependants.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The deployed hash equals T3's candidate and T6's deployment package in 100% of
  releases (D-6).
- **SC-002**: A model swap under steady traffic leads to a drift event and an open T9 run within
  10 minutes (demo time scale), with the measured value in the event (D-7).
- **SC-003**: A stage breach rolls traffic back to stable in 100% of trials.
- **SC-004**: T6–T9 controls that read `change`, `release`, `telemetry`, `retirement` and `env.prod`
  use real records (not synthetic) in 100% of runs where the tools ran.
- **SC-005**: With scripted replies, the reference use case reaches T8's first review and a T9
  re-entry in 100% of offline replays.
- **SC-006**: 0 out-of-scope tool calls reach a system; every refusal is recorded.
- **SC-007**: The feature 001–011 suites still pass (CI).

## Assumptions

- Live runs use the dev model profile; the platform's deterministic parts are what the success
  criteria measure, as accepted for features 008 and 011.
- T8's review periods run at the demo time scale.
- Feature 013 (dashboard) shows the journey; this feature records what it needs.
