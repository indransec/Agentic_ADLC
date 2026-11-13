# Feature Specification: End-to-End Demo

**Feature Branch**: `014-e2e-demo`

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: "Feature 014 e2e-demo (build plan §6 row 014; SA §21 validation and
demo plan; SA §16 quality attributes; MVP acceptance criteria): scenario tests for D-1 to D-9,
resilience tests, demo script and data reset, rehearsal fixes. Must do; no simplification."

## Clarifications

### Decided before this feature (recorded for context)

- Scenario tests already exist for D-2, D-3, D-4, D-5, D-7, D-9 and the happy path (features
  003–008); the reference use case replays offline from T0 to T9 (D-6, D-7; features 011–012);
  the dashboard shows the journey live (D-8; feature 013).
- Restart, redelivery and dead-letter behaviour is tested inside one process (feature 003).
- The demo use case is the Incident Triage reference (`it-service-desk`) on the pilot (009).
- The dev model (GPT-4o mini) does not carry T2–T5 reliably (accepted in 008 and 011).

### Session 2026-11-13

- Q: How do the agents answer during the demo? → A: A demo driver runs the SA §21 script on the
  full stack with the agents' replies from rehearsed recordings (the same platform, tools, pilot
  and checks; only the model's text is replayed), so the demo is repeatable; `--live` switches the
  agents to the configured model profile.
- Q: Who performs the human steps? → A: The presenter in the web app; the driver waits at each
  human step, says what to do, where and as which role, and continues when it is done; `--auto`
  makes the driver take the steps itself (rehearsals, CI).
- Q: What does the demo data reset clear? → A: Everything platform-side (database volume,
  re-migrate, register specs, accounts, pilot state, enterprise mocks) via `make demo-reset`,
  refused unless `ADLC_ENV=demo`, and confirmed.

## User Scenarios & Testing *(mandatory)*

The MVP is accepted when D-1 to D-9 are shown live, every decision is traceable in the ledger to
its spec version, actor and evidence hash, all scripted scenarios pass, and no agent can set an
outcome or deploy an unauthorised hash (SA §21). This feature makes that demonstration repeatable
and proves it in tests.

### User Story 1 – The demo script runs end to end (Priority: P1)

A presenter resets the demo environment, starts the driver and follows the ten SA §21 steps in
the web app: T0 submitted and passed; T1 rejected with a comment and reworked; T2 asks a
clarification that is answered and the same run resumes; T3 builds the candidate; T4 finds a
defect routed back to T3; T5's kill-switch gap is accepted with a waiver; T6 verifies the chain
and the change is approved; T7 rolls out canary then full; T8 runs traffic and the model swap
raises drift; T9 classifies and re-enters at T2; one terminal is driven to escalation by repeated
rejection; the dashboard shows it all live.

**Why this priority**: the MVP gate.

**Independent Test**: In auto mode on a reset environment, the driver completes all steps and
reports each demo moment as shown, with the run ids that prove it.

**Acceptance Scenarios**:

1. **Given** a reset demo environment, **When** the driver runs, **Then** every step completes in
   order and the final report lists D-1 to D-9 each with its evidence (runs, events, decisions).
2. **Given** a human step, **When** the presenter has not acted, **Then** the driver waits and
   says what to do, where, and as which role.
3. **Given** a step fails (a control fails unexpectedly, a service is down), **Then** the driver
   stops with the reason and how to resume from that step.

---

### User Story 2 – Every demo moment has a scenario test (Priority: P1)

D-1 to D-9 each have an offline scenario test (no external model, no running stack), so CI proves
the platform behaviour behind every moment.

**Independent Test**: The scenario suite passes in CI; each test names the moment it proves.

**Acceptance Scenarios**:

1. **Given** D-1, **Then** at every terminal an agent built, the reviewer recommended, and a
   person decided, each recorded.
2. **Given** D-6, **Then** the deployed hash equals T3's candidate, T4's and T5's bound hash and
   T6's authorised package.
3. **Given** D-8, **Then** the dashboard's journey, activity and KPIs reflect a scripted lifecycle.
4. **Given** the negative tests, **Then** no agent sets an outcome or deploys an unauthorised hash.

---

### User Story 3 – Resilience on the running stack (Priority: P1)

The orchestrator is restarted mid-run, an event is delivered twice, and a routing failure
dead-letters an event that the CoE re-queues; the lifecycle continues with nothing lost or done
twice.

**Independent Test**: A resilience script on the running demo stack restarts the orchestrator
container during a build, replays an already-processed event, and forces a dead letter; each
check reports pass with evidence.

---

### User Story 4 – Traceability check (Priority: P2)

After the demo, every decision of the use case is traceable to its spec version, actor and
evidence hash, and the ledger verifies.

**Independent Test**: A traceability report over the demo use case: every sign-off, control
decision, routing event and artifact version links to a spec version, an actor and a hash; the
hash chain verifies.

---

### User Story 5 – Rehearsal fixes (Priority: P2)

Issues found in rehearsals (timing, wording, UI friction, flaky steps) are fixed and recorded.

**Independent Test**: Two consecutive rehearsals on a reset environment complete without manual
intervention beyond the scripted human steps.

### Edge Cases

- The model gateway is down in live mode: the run waits (feature 006 outage handling); the driver
  reports it and offers to continue with recordings.
- The demo clock: timers compressed by the time scale; the driver never waits on real days.
- A step is repeated after a stop: the driver resumes from the use case's current state.
- The reset is run outside the demo environment: refused.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A demo driver MUST run the SA §21 script on the full stack, step by step, reporting
  each step's outcome and each demo moment's evidence.
- **FR-002**: Agent replies during the demo MUST come from rehearsed recordings by default (the
  platform, tools, pilot and checks run for real), and from the configured model with `--live`.
- **FR-003**: Human steps MUST be taken by the presenter in the web app, the driver waiting and
  saying what to do; with `--auto` the driver takes them. Either way they go through the
  platform's service operations (authorized, logged, recorded).
- **FR-004**: `make demo-reset` MUST clear all platform-side data (database volume, migrations,
  specs, accounts, pilot state, enterprise mocks) and bring the stack back up, refusing unless
  `ADLC_ENV=demo` and confirmed.
- **FR-005**: Each of D-1 to D-9 MUST have an offline scenario test in CI.
- **FR-006**: Negative tests MUST show that no agent can set an outcome or deploy an unauthorised
  hash.
- **FR-007**: Resilience checks MUST cover orchestrator restart mid-run, duplicate delivery and
  dead-letter handling on the running stack.
- **FR-008**: A traceability report MUST show every decision linked to spec version, actor and
  evidence hash, and the ledger verification result.
- **FR-009**: No terminal or use-case names in platform code; the demo script and data are data.

### Key Entities

- **Demo step**: number, terminal, actions (agent, human, fault), expected result, demo moments.
- **Demo report**: steps with outcome and evidence; moments D-1 to D-9 with proof.
- **Resilience check**: name, action, expected result, evidence.

## Success Criteria *(mandatory)*

- **SC-001**: In auto mode, the demo completes on a reset environment in under 20 minutes, two
  rehearsals in a row.
- **SC-002**: D-1 to D-9 each have a passing offline scenario test (9 of 9).
- **SC-003**: The three resilience checks pass on the running stack.
- **SC-004**: 100% of the demo use case's decisions are traceable; the ledger verifies.
- **SC-005**: 0 agent actions set an outcome or deploy an unauthorised hash in negative tests.
- **SC-006**: The earlier suites still pass (CI).

## Assumptions

- The demo runs on one host with the compose stack; time scale set for the demo.
