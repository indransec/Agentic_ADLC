# Feature Specification: Terminal Agents T3–T5

**Feature Branch**: `011-terminal-agents-t3-t5`

**Created**: 2026-11-12

**Status**: Draft

**Input**: User description: "Feature 011 terminal-agents-t3-t5 (build plan §6 row 011; SA §7
agent architecture, §13 integration): turn the T3, T4 and T5 terminal agents from stubs into real
model agents that act through feature 010's MCP tools: T3 fills the golden template and builds a
candidate package in dev, T4 evaluates the candidate in test and keeps a regression pack, T5
assures it with red-team, personal-data and control evidence and uses the waiver path when a gap
is accepted."

## Clarifications

### Decided before this feature (recorded for context)

- Tools, scopes, run tokens and bound values come from feature 010; the evaluation is the
  deterministic harness and the fixed red-team suite (no DeepEval, garak or PyRIT).
- T3 fills configuration only; the agent code and infrastructure definitions are fixed in the
  golden template (009). Environments are provisioned only through the pilot's operations (010).
- The exception and waiver path exists already (features 003, 007): a human decides an exception
  with waiver owner, expiry and compensating control; the reviewer recommends.
- Subagents: none by default (SA §7.1 allows T3 up to two); the single-agent tool loop of
  features 006 and 008 is used.

### Session 2026-11-12

- Q: How does the T3 agent produce the fill? → A: The use case's repository starts with the
  golden template's example fill on `main`; T3 adapts it to the T1 requirements and T2 design
  (instructions, routing rules, tool bindings, thresholds, settings) on its branch, and CI decides
  whether the result is valid.
- Q: Where do the measured numbers in T3–T5 artifacts come from? → A: The agent writes them from
  its tool results, and a deterministic control compares each measured value with the evidence the
  platform recorded for the run (feature 010's tool results); a mismatch fails the control and
  names the row.
- Q: What is "judge calibration" in T4 when scoring is deterministic? → A: The judge is the
  harness's deterministic scorer; calibration compares it with the dataset's human-reviewed labels
  on a labelled slice and reports the measured agreement and the slice size. No LLM judge in this
  feature.

## User Scenarios & Testing *(mandatory)*

Until now T3–T5 are stubs that return synthetic artifacts, and controls such as "CI green",
"red-team injection rate within the tier maximum" and "no personal-data leak" read synthetic
evidence. With this feature the build, evaluation and assurance of the pilot are done by agents
acting on real systems through scoped tools, and the controls read what those systems recorded.

### User Story 1 – T3 builds a candidate package from the approved design (Priority: P1)

After T2 passes, the T3 agent fills the golden template for the use case on its own branch,
runs CI, provisions the dev environment with the built package, checks that it emits telemetry,
and produces the build artifacts with the candidate package hash.

**Why this priority**: Every later terminal needs a candidate package (D-6); T3 is the first
terminal that acts on systems.

**Independent Test**: Open T3 for a use case whose T2 passed (with recorded agent replies); check
the branch, the CI evidence, the dev environment, the artifacts and that the candidate hash is
the one CI built.

**Acceptance Scenarios**:

1. **Given** T2 passed, **When** T3 runs, **Then** the agent writes the fill on the run's branch,
   opens a pull request, runs CI until it is green (or reports why not), creates the dev
   environment with the built hash, and returns all mandatory T3 artifacts, with
   `candidate_package.sha256` equal to CI's hash.
2. **Given** CI fails on the agent's fill, **When** the agent reads the failing part, **Then** it
   corrects the fill and runs CI again, within its step limit; if it cannot, the run escalates
   with the CI reason.
3. **Given** T3's controls, **When** they run, **Then** "CI green", "secret scan clean", "SAST
   clean", "coverage" and "SBOM" read the CI evidence recorded for this run, not synthetic data,
   and the decision says so.
4. **Given** T4 later finds a defect with root cause "implementation", **When** T3 re-runs,
   **Then** the agent receives the defect log and changes the fill accordingly.

---

### User Story 2 – T4 evaluates the candidate against the T1 thresholds (Priority: P1)

The T4 agent provisions the test environment with the candidate (bound by the platform), runs the
registered golden and regression datasets through the harness, compares the results with T1's
evaluation and RAI thresholds, the T2 token budget and the T1 latency requirement, logs defects
with a root-cause terminal, and records the regression pack.

**Why this priority**: D-3 (rework routed to the right terminal) and the pass decision for
evaluation depend on it.

**Independent Test**: Run T4 on a candidate that meets the thresholds and on one that does not
(a weaker fill); check the artifacts, the controls and the recommended outcome.

**Acceptance Scenarios**:

1. **Given** a candidate in test, **When** T4 runs, **Then** every T1 evaluation and RAI
   threshold has a row with the measured value taken from the harness run, and the controls pass
   only when every measured value meets its threshold.
2. **Given** a weaker candidate, **When** T4 runs, **Then** the threshold control fails with the
   metric named (every copied value still matching the recorded result), the run escalates
   because the agent cannot fix a measured shortfall, and a person completes the escalation and
   decides rework with root cause "implementation", which routes to T3 (features 003, 007).
3. **Given** the regression dataset, **When** T4 records the regression pack, **Then** it names
   the dataset id, version and case count, and later terminals can re-run it.
4. **Given** the judge calibration control, **When** it runs, **Then** it reads a measured
   agreement and a labelled-slice size that meet the tier minimums.

---

### User Story 3 – T5 assures the candidate and accepts gaps only by waiver (Priority: P1)

The T5 agent runs the red-team suite and the personal-data scan against the candidate in test,
reads the control library and the agent's identities and permissions, builds the threat model,
privacy assessment, regulatory map, RAI assurance and residual risk register, files the
assurance report, and, when a control gap remains, the reviewer recommends an exception that a
person can accept with a waiver.

**Why this priority**: D-5 (exception with waiver) and the T6 evidence chain depend on it.

**Independent Test**: Run T5 on a clean candidate and on one with a known gap; check that the
controls read the red-team and scan evidence, and that the gap ends as an exception with a waiver
decided by a person.

**Acceptance Scenarios**:

1. **Given** a candidate in test, **When** T5 runs, **Then** the injection and jailbreak rates and
   the personal-data finding count that T5's controls read come from the run's red-team and scan
   results.
2. **Given** a gap the agent cannot close (for example a masking gap in logs), **When** the
   reviewer recommends, **Then** it recommends an exception with the waiver fields filled, and the
   run closes as an exception only after the waiver approver accepts it.
3. **Given** the assurance attestation, **When** T5 passes, **Then** the attestation row is the
   human sign-off, never written by the agent.

---

### User Story 4 – Agents act only through their terminal's tools (Priority: P1)

T3 can write its branch, run CI and provision dev; T4 and T5 can provision test with the
candidate only; none can deploy, change the split or touch another terminal's tools.

**Why this priority**: Constitution IV and XI; the first agents with write tools.

**Independent Test**: Script agent replies that ask for out-of-scope tools; check refusals,
records, and that nothing reached the pilot.

**Acceptance Scenarios**:

1. **Given** a T3 agent that asks for `cd_deploy` or for the test environment, **When** it calls,
   **Then** the call is refused and recorded, and the agent continues or escalates.
2. **Given** any of the three agents, **When** a tool's output contains instructions, **Then** the
   agent treats them as data (the reply is checked against its artifacts' schema; no status or
   permission changes).

---

### User Story 5 – The CoE measures the agents on reference use cases (Priority: P2)

The reference use cases of feature 008 are extended through T3–T5, with recorded replies for
offline tests and a live replay that reports artifact quality, reviewer agreement, tool calls and
cost per terminal.

**Why this priority**: SA §7.4: lifecycle agents are evaluated after any prompt, playbook or model
change.

**Independent Test**: Replay the reference use cases offline and check every terminal reaches
sign-off with valid artifacts; run the live replay on the dev model and read the report.

**Acceptance Scenarios**:

1. **Given** recorded replies, **When** the replay runs offline, **Then** T3–T5 reach sign-off with
   schema-valid artifacts and the same tool calls each time.
2. **Given** the dev model, **When** the live replay runs, **Then** the report shows per terminal
   the artifacts' validity, control results, reviewer recommendation, tool calls and cost.

---

### Edge Cases

- CI never turns green within the step limit: the run escalates with the last CI reason.
- The dev or test host is down: the tool says so; the agent reports it as a clarification or
  escalation, never as success.
- A T1 threshold names a metric the harness does not measure: the row says "not measured" and
  the threshold control fails, so the gap is visible (and can be waived).
- A measured value in an artifact differs from the recorded tool result: the evidence control
  fails and names the row.
- The agent asks for a dataset that is not registered: refused by the tool; the agent uses the
  registered list.
- T4 re-runs after rework: it evaluates the new candidate hash, never the previous one.
- A red-team rate exceeds the tier maximum: the control fails; the only path to proceed is rework
  or an exception with a waiver.
- The kill switch cannot be tested in the test environment (it exists only in prod-sim, and T5
  holds no kill-switch scope): T5 reports the kill-switch scenario as not run, the control fails,
  and the path is an exception with a waiver whose compensating control is the kill-switch check at
  release (T7).

## Requirements *(mandatory)*

### Functional Requirements

**Agents**

- **FR-001**: T3, T4 and T5 MUST be model agents with versioned prompts and playbooks, bound in
  the agents catalogue to the tools their terminal's spec grants (feature 010 scopes), and MUST
  return every mandatory artifact of their terminal with the declared columns.
- **FR-002**: Each agent MUST read its prerequisites' evidence (T1 requirements and thresholds, T2
  design and budget, T3 manifest for T4/T5, T4 results for T5) from the context pack, and rework
  context (defect log, owner comment) when it runs again.
- **FR-003**: Agents MUST NOT write outcome statuses, approvals or the T5 attestation; those stay
  with people (constitution III).

**T3 build**

- **FR-004**: T3 MUST produce the fill on its branch, open a pull request, run CI, provision the
  dev environment with CI's package hash and report `candidate_package.sha256` equal to that hash.
- **FR-005**: CI MUST report the checks T3's controls read: status (green only if every check
  passed), test results with coverage, SAST and secret-scan counts, and an SBOM with licence
  approval; these MUST be recorded as evidence for the run.

**T4 evaluation**

- **FR-006**: T4 MUST run at least the registered golden and regression datasets against the
  candidate in test and write one row per T1 evaluation and RAI threshold with the measured value
  and the result; unmeasured metrics MUST be stated as such.
- **FR-007**: T4 MUST log defects with severity and root-cause terminal, record the regression
  pack (dataset id, version, case count) and report cost and p95 latency against the T2 budget
  and the T1 latency requirement.
- **FR-008**: T4 MUST report the judge calibration as measured agreement on a labelled slice with
  its size.

**T5 assurance**

- **FR-009**: T5 MUST run the red-team suite and the personal-data scan on the candidate and
  produce the threat model results, security control evidence (citing control-library ids),
  access-control matrix, privacy assessment, regulatory map, RAI assurance, resilience
  verification and residual risk register, and file the assurance report in GRC.
- **FR-010**: The evidence sources `redteam` (injection and jailbreak success rates) and `dlp`
  (personal-data findings) MUST be read from the run's recorded results.

**Evidence and checks**

- **FR-011**: The evidence sources `ci` and `sbom` MUST be read from the latest CI result recorded
  for the use case's candidate; synthetic evidence remains the labelled fallback only when no
  result exists.
- **FR-012**: Measured values that agents copy into artifacts (CI status and counts, metric
  actuals, cost and latency, red-team rates, personal-data findings, calibration agreement) MUST
  be checked by deterministic controls against the tool results recorded for the run; a mismatch
  fails the control and names the row.
- **FR-014**: The use case's repository MUST start with the golden template's example fill on
  `main`, so T3 adapts a valid fill rather than writing one from nothing.

**Reference use cases**

- **FR-013**: The 008 reference use case whose pilot matches the golden template (the incident
  triage one) MUST be extended through T3–T5 with recorded replies for offline tests (the others
  stay at T2), and the live replay MUST report, per terminal, artifact validity, control
  results, reviewer recommendation, tool calls and cost.

### Key Entities

- **Fill**: the files T3 writes on its branch (feature 009's fill points).
- **CI result**, **harness result**, **red-team result**, **scan result**: feature 010's recorded
  evidence results for a run.
- **Regression pack**: a registered dataset (id, version, case count) T4 names for later re-runs.
- **Defect**: severity, root-cause terminal, status.
- **Waiver**: owner, expiry, compensating control (feature 003).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With recorded replies, a reference use case goes from T3 to T5 sign-off with
  schema-valid artifacts in 100% of offline replays.
- **SC-002**: T3's candidate hash equals the CI-built hash and the dev environment runs it in
  100% of runs that pass.
- **SC-003**: The controls of T3, T4 and T5 that read `ci`, `sbom`, `redteam` and `dlp` use real
  recorded results (not synthetic) in 100% of runs where the tools ran.
- **SC-004**: A weaker candidate fails at least one T4 threshold control and, decided as rework
  with root cause "implementation", returns to T3 in 100% of trials.
- **SC-005**: An artifact whose measured value differs from the recorded result fails its
  evidence check in 100% of trials.
- **SC-006**: 0 out-of-scope tool calls reach a system; every refused call is recorded.
- **SC-007**: A live replay on the dev model completes T3–T5 for the reference use case and reports
  cost per terminal.
- **SC-008**: The feature 001–010 suites still pass.

## Assumptions

- The dev model profile (GPT-4o mini) is used for live replays, as in feature 008; recorded
  replies make offline tests deterministic.
- T6–T9 stay stubs until feature 012.
- The pilot's CI (pilot-lab) is extended to report test results, coverage, scans and an SBOM
  (FR-005); these are measured on the template and the fill, not on external code.
- Spec changes for new evidence checks follow the spec rules (a changed value is a major version).
