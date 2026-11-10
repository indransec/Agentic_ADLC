# Feature Specification: Policy Engine

**Feature Branch**: `004-policy-engine`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "Feature 004 policy-engine: the deterministic policy engine (build plan
§6 row 004; SA §9, §5.4, §5.1; constitution IV, VI, X, XI). Evaluates prerequisites, automated
controls and conditions from the pinned specs, authorizes actions, resolves parameters within
guardrails, logs every decision, and replaces the stub policy in the running orchestrator."

## Clarifications

### Session 2026-11-10

- Q: Should synthetic evidence be used in the running stack until features 009–012 exist, and
  how are decisions that read it marked? → A: On in dev and demo. Every decision that read
  synthetic evidence is labelled `synthetic` in its decision record and in the run's control
  results, so an auditor or approver can see that a gate was passed on stand-in data.

## User Scenarios & Testing *(mandatory)*

Every rule that can be computed is decided by the policy engine, outside the models
(constitution VI). The engine reads the rule from the use case's pinned spec, reads the
evidence the rule needs, decides, explains its decision, and records it. When it cannot decide
(missing evidence, an error, an unknown name), the answer is "not passed", with the reason
(constitution XI).

### User Story 1 - Prerequisites are checked at run open (Priority: P1)

When a terminal run opens, the orchestrator asks the policy engine to check each prerequisite
in the pinned spec. A prerequisite reads evidence about the use case: earlier terminals'
records (status, signatures, close time) and artifacts, the intake, and the triggering event.
The engine answers passed or not passed, with a reason. A run whose blocking prerequisite is
not passed waits in `blocked` (feature 003).

**Why this priority**: entry conditions are the first gate of every run (SA §9). Without
them, a run could start on missing or rejected evidence.

**Independent Test**: open T1 for a use case whose T0 passed with a risk classification; every
T1 prerequisite passes. Open T1 for a use case whose T0 has no risk classification; the
matching prerequisite fails with a reason naming the missing evidence, and T1 is blocked.

**Acceptance Scenarios**:

1. **Given** a use case whose T0 closed with `pass` and a risk classification table with a tier
   column, **When** T1 opens, **Then** each T1 prerequisite is passed and the run starts
   building.
2. **Given** a use case whose T0 risk classification is missing, **When** T1 opens, **Then**
   the prerequisite that needs it is not passed, the reason names the missing evidence, and
   the run is `blocked`.
3. **Given** a prerequisite with `on_missing: warn` that is not passed, **When** the run opens,
   **Then** the run proceeds and the warning is recorded.
4. **Given** a terminal with more than one closed run (for example after rework), **When** a
   later terminal reads its evidence, **Then** the latest closed run's record and artifacts are
   used.

---

### User Story 2 - Automated controls are enforced on every build attempt (Priority: P1)

After every agent build attempt, the orchestrator asks the engine to check each automated
control of the pinned spec. Controls are rules over the run's artifacts, resolved parameters
and evidence; the specs call named checks from the predicate catalogue (for example "every row
has a numeric baseline and target"). Blocking controls that are not passed send the run back
for an automatic retry (feature 003). Advisory controls are recorded only.

**Why this priority**: controls are what make an artifact acceptable before a reviewer or a
person looks at it (constitution VI). Every predicate the specs call must work, or a terminal
cannot close.

**Independent Test**: give T1 artifacts in which every requirement has an id, a priority and
acceptance criteria and every KPI has numeric baseline and target values. Every T1 blocking
control passes. Remove one KPI's baseline: control CTL-T1-02 fails with a reason naming the
table, the column and the failing row.

**Acceptance Scenarios**:

1. **Given** artifacts that meet every control, **When** controls are checked, **Then** every
   blocking control passes and the run moves to review.
2. **Given** an artifact table with a missing or non-numeric value, **When** the matching
   control is checked, **Then** it fails, and the reason names the table, column and row.
3. **Given** an advisory control that fails, **When** controls are checked, **Then** the
   failure is recorded and does not block the run.
4. **Given** a control that compares an artifact value with a parameter (for example
   autonomy level at most the maximum for the tier), **When** it is checked, **Then** the
   resolved parameter for the use case's tier is used.
5. **Given** a control that needs evidence that is not available yet (for example red-team
   results before that feature exists), **When** it is checked, **Then** it fails with the
   reason "evidence not available: <source>", unless a synthetic evidence source supplies it.

---

### User Story 3 - Parameters resolve within enterprise guardrails (Priority: P1)

Controls compare artifacts with parameters (`param.*`). Each parameter resolves in the order
of SA §5.4:

1. the use case's own value, if it is within the guardrail for its risk tier;
2. otherwise, the guardrail's default for that tier.

A guardrail marked tighten-only can be made stricter by a use case, never looser. Loosening
needs an exception. The resolved set is frozen on the run for audit.

**Why this priority**: guardrails are what no use case may cross (SA §5.1). Resolving them
wrongly would let a use case pass a gate with a weaker limit.

**Independent Test**: for a `max` guardrail with tier default 0.02, a use case value of 0.01
is used; a value of 0.05 is not used (0.02 applies) and the attempt is recorded. With no use
case value, 0.02 applies.

**Acceptance Scenarios**:

1. **Given** a tighten-only maximum of 0.02 for the tier, **When** the use case proposes 0.01,
   **Then** 0.01 is used.
2. **Given** the same guardrail, **When** the use case proposes 0.05, **Then** 0.02 is used,
   and the rejected value is recorded with the reason.
3. **Given** a tighten-only minimum of 80, **When** the use case proposes 90, **Then** 90 is
   used; 70 is rejected and 80 is used.
4. **Given** a run that opens, **When** its parameters are resolved, **Then** the resolved
   values, with their source (use case or guardrail), are recorded once for the run and reused
   for every check of that run.
5. **Given** a use case with no risk tier yet (before T0 passes), **When** parameters resolve,
   **Then** the `medium` tier values apply (as for timers in feature 003).

---

### User Story 4 - Every decision is recorded and explainable (Priority: P1)

An auditor or the ADLC CoE can see every decision the engine made: which rule or action, the
check it belongs to, the inputs it read, the result, the reason, the run and the time.
Records are never changed.

**Why this priority**: the ledger of decisions is what makes a gate auditable (constitution V
and X). A decision that leaves no record cannot be defended.

**Independent Test**: run a use case through T1. For each prerequisite and control checked,
there is one decision record with the inputs read and the result. Attempts to change or
delete a decision record are refused.

**Acceptance Scenarios**:

1. **Given** any check or permission decision, **When** it is made, **Then** one decision
   record is written with rule or action, check id, inputs read (values or references), result,
   reason, run and time.
2. **Given** a decision record, **When** anyone tries to change or delete it, **Then** it is
   refused.
3. **Given** a run, **When** someone reads its decisions, **Then** they are listed in order,
   so a failed attempt can be explained.

---

### User Story 5 - The running platform enforces real rules (Priority: P1)

The orchestrator process uses the real policy engine instead of the stub from feature 003.
Until real agents arrive (feature 006), the stub agent produces realistic synthetic artifacts
for each terminal, which meet the controls. These are kept as data files, not code. A full
T0→T9 lifecycle and the demo moments still run end to end, now with real checks. Tests can
supply failing artifacts to see a gate refuse.

**Why this priority**: the platform must be honest from here on. A gate that only passes
because the policy is a stub proves nothing.

**Independent Test**: run the feature 003 scenarios (happy path, D-2, D-3, D-4, D-5, D-7,
D-9) with the real engine and the synthetic artifacts; all pass. Replace one synthetic artifact
with a bad one; the run retries and then escalates with the retry-limit trigger.

**Acceptance Scenarios**:

1. **Given** the orchestrator process, **When** it starts, **Then** it uses the real policy
   engine.
2. **Given** synthetic artifacts for every terminal, **When** a use case runs T0→T9, **Then**
   every blocking prerequisite and control passes.
3. **Given** a synthetic artifact that breaks a blocking control, **When** the run is built,
   **Then** the control fails with its reason, and the run retries and then escalates.

---

### User Story 6 - Actions are authorized against the terminal's permissions (Priority: P2)

Before an agent or a tool server acts (features 006 and 010), it asks the engine whether the
actor may perform the action on the resource. The terminal's allow and deny lists decide, and
deny wins. Permission is scoped to the run: an actor working on one run cannot act for
another. A refusal carries a reason.

**Why this priority**: separation of duties (constitution IV) is enforced at run time here.
Agents with tool calls arrive in 006, so this is needed before then but not by the 003 flow.

**Independent Test**: for T1's agent on its own run, "write T1 artifacts" is allowed, "write
the T0 ledger record" is denied (deny list), and "write T1 artifacts" for another use case's
run is refused as out of scope.

**Acceptance Scenarios**:

1. **Given** an action matched by the terminal's allow list and not by its deny list, **When**
   authorization is asked, **Then** it is allowed.
2. **Given** an action matched by both lists, **When** authorization is asked, **Then** it is
   denied, with the deny entry as the reason.
3. **Given** an action matched by neither list, **When** authorization is asked, **Then** it is
   denied (default deny).
4. **Given** an actor bound to one run, **When** it asks to act for a different run, **Then**
   it is refused.
5. **Given** a tool scope listed for the terminal, **When** the agent asks to use that tool,
   **Then** it is allowed; any other tool is refused.

---

### User Story 7 - Conditions on approvers and follow-on events (Priority: P2)

The orchestrator asks the engine whether conditional rules hold:

- a conditional approver (for example the solution architect when the build deviates from the
  design);
- an external approval body (for example the CAB when the tier requires one);
- an operational event's follow-on (for example rollback when an incident is severity 1).

**Why this priority**: these conditions change who must approve and what happens next. In
feature 003 the stub answered "yes" to all of them.

**Independent Test**: an incident event with severity `sev1` produces the rollback follow-on;
`sev3` does not. A T3 design-conformance table with a deviation requires the solution
architect; one without deviation does not.

**Acceptance Scenarios**:

1. **Given** a conditional approver rule, **When** its condition holds, **Then** the approver is
   required; otherwise, not.
2. **Given** an event route with a follow-on condition, **When** the triggering event matches
   it, **Then** the follow-on is written; otherwise, not.
3. **Given** a condition that cannot be evaluated, **When** it is asked, **Then** the answer is
   "holds" for approvers and external bodies (more approval, never less), and "does not hold"
   for follow-on events, with the reason recorded.

### Edge Cases

- **A rule names a terminal with no closed run for the use case** (for example a T1
  prerequisite before T0 closed): the evidence is missing, and the check is not passed.
- **An artifact table is empty**: "every row" checks fail with the reason "table is empty". A
  required artifact must have rows, which the applicable-artifacts check also enforces.
- **A value that should be numeric is text** (for example "80%"): the numeric check fails with
  the row named. Numbers given as text without units ("80") count as numbers.
- **A predicate is called with arguments of the wrong kind**, or a function is not in the
  catalogue: not passed, with the reason. Feature 002 validation should prevent both.
- **A duration comparison involves a timeline value that is not a duration** (T7's
  `window_end`): not passed, with the reason. The window is evaluated by the deployment feature.
- **A guardrail has no value for the tier**: the parameter is unresolved, and every check that
  needs it is not passed.
- **A terminal spec has no allow list**: every action is denied.
- **A rule takes too long or grows too large**: it is stopped and not passed.
- **The same check is repeated within one attempt**: each call is recorded.

## Requirements *(mandatory)*

### Functional Requirements

**Evaluation**

- **FR-001**: The engine MUST evaluate the expressions written in terminal specs
  (prerequisites, automated controls, approver conditions, external-body conditions, event
  follow-on conditions) in the expression language the 002 toolkit validates, using the
  namespaces it allows: terminal evidence `T<n>.*`, `param.*`, `tier.*`, `timeline.*`, `run.*`
  and the catalogued evidence sources (`intake`, `trigger`, `profile`, `env`, `ci`, `sbom`,
  `redteam`, `dlp`, `telemetry`, `change`, `template`, `dataset`, `release`, `portfolio`,
  `retirement`).
- **FR-002**: Every predicate in the predicate catalogue MUST have an implementation that
  takes its catalogued parameters and returns its catalogued type. A call to a name outside
  the catalogue MUST be refused.
- **FR-003**: Every evaluation MUST return passed or not passed, the value computed, and a
  reason. For a failure, the reason names what failed (for example table, column and row, or
  the missing evidence). When several parts fail, the first failing predicate's reason is
  reported.
- **FR-004**: The engine MUST fail closed. An error, missing evidence, a wrong type, an unknown
  name, or an evaluation that exceeds its time or size limit MUST give "not passed" with the
  reason. It MUST never raise an error that lets a gate through. The limits are 1 second per
  evaluation, 10,000 rows per table and 100,000 characters per text value.
- **FR-005**: Expressions MUST be evaluated without side effects. They can only read the
  evidence given to them.
- **FR-006**: Prerequisites and automated controls MUST be evaluated for every check the
  orchestrator asks about, keeping the blocking and advisory distinction of feature 003 (a
  blocking prerequisite blocks; a blocking control causes a retry; others are recorded).

**Evidence**

- **FR-007**: Evidence MUST be read through an evidence-provider interface. The provider
  answers per source with a value, or "not available".
- **FR-008**: Terminal evidence `T<n>.<field>` MUST come from the latest closed run of
  terminal `T<n>` for the same use case:
  - record fields from the evidence source catalogue (status, signatures, close time, run
    version, waivers);
  - artifacts as `T<n>.<artifact>` (a table of rows) and `T<n>.<artifact>.<column>` (the first
    row's value);
  - emitted values as `T<n>.<name>` (the values of its pass decision, for example
    `T4.eval_baseline`);
  - `T<n>.bound_to`, the spec's `ledger.bound_to` reference resolved for the use case (for
    example the T3 package hash).

  The run being checked reads its own artifacts the same way, under its own terminal id.
- **FR-009**: `intake` (the submitted use case), `trigger` (the event that opened the run) and
  `run.*` (rework count, age, mode, use case, run version, risk tier) MUST be provided from
  feature 003's records. The directory (for `in_directory`) is the account file, mounted
  read-only into the orchestrator; without it, the synthetic provider supplies it, labelled.
- **FR-010**: Sources built by later features MUST answer "not available" until those features
  register a real provider. A synthetic provider MUST be able to supply any source for tests
  and the demo. The sources are `env`, `ci`, `sbom`, `redteam`, `dlp`, `telemetry`, `change`,
  `template`, `dataset`, `release`, `portfolio` and `retirement`, and `profile` until feature
  005.
- **FR-011**: `timeline.*` MUST come from the pinned spec's timeline for the use case's tier,
  and `tier.*` from the risk tier catalogue. Durations MUST compare as durations.

**Parameters**

- **FR-012**: `param.<name>` MUST resolve per SA §5.4:
  1. the use-case value, when the use case's profile supplies one within the guardrail for the
     use case's tier;
  2. otherwise, the guardrail's tier value.
- **FR-013**: A use-case value is "within the guardrail" when it is numeric and stricter than
  or equal to the tier value: lower for a `max` guardrail, higher for a `min` one. This applies
  to every guardrail. A tighten-only guardrail can only be loosened by an exception, never by a
  profile value. A value that is not within the guardrail MUST be rejected, and the rejection
  recorded with the guardrail, the proposed value and the reason.
- **FR-014**: The resolved parameter set MUST be computed when the run opens, recorded with
  each value's source, and reused for every check in that run. Each run resolves its own set
  (a rework run does not reuse the previous run's). A use case without a tier MUST use the
  `medium` values.

**Authorization**

- **FR-015**: `authorize(actor, action, resource, run)` MUST allow an action only when the
  run's terminal spec allows it and does not deny it. Deny wins, and the default is deny.
  - Actions and resources follow the permission patterns of the spec (`<verb>:<resource>`,
    with `*` wildcards).
  - Tool use follows the terminal's tool scopes, and the deny list still applies to it.
  - People are authorized by sign-off roles in feature 003, not by `authorize`.
- **FR-016**: Authorization MUST be run-scoped: an actor bound to a run may act only for that
  run's use case and terminal. Any other request is refused. Agent, reviewer and tool actors
  are named `<kind>:<run id>`. Feature 003's agent and reviewer actor ids change from
  `<kind>:<terminal>` to this form.
- **FR-017**: A refusal MUST name the matching deny entry, or say that no allow entry matched,
  or that the request is out of scope.

**Conditions used by the orchestrator**

- **FR-018**: The engine MUST answer the orchestrator's conditional checks:
  - conditional approvers (`plus` conditions);
  - external approval bodies;
  - event follow-on conditions.

  When such a condition cannot be evaluated:
  - for approvers and external bodies, the answer MUST be "holds" (fail safe toward more
    approval);
  - for follow-on events, the answer MUST be "does not hold".

  Either way, the reason is recorded.

**Decision log and tracing**

- **FR-019**: Every evaluation and authorization MUST write one decision record. A record holds:
  - the rule or action and the check id;
  - the inputs read: scalar values in full, tables as a reference with row count and content
    hash;
  - the result, the value and the reason;
  - the run, the use case and the time.
- **FR-020**: Decision records MUST be append-only for every identity, and MUST be kept even if
  the caller's work is rolled back. There is one record per check per attempt, kept with the
  run.
- **FR-021**: The decisions of a run MUST be readable in the order they were made.
- **FR-022**: Every evaluation and authorization MUST be traced with the run id (constitution X).
  A conditional artifact's `when`, evaluated inside the applicable-artifacts check, is recorded
  as its own decision.

**Platform wiring**

- **FR-023**: The orchestrator process MUST use the real policy engine through the feature 003
  policy interface. The interface's only change is a backward-compatible `synthetic` field
  (default false) on evaluation results.
- **FR-024**: The stub agent MUST produce synthetic artifacts per terminal that meet the
  registered specs' controls. These MUST be kept as data files, not code. Tests MUST be able to
  override them with failing artifacts.
- **FR-025**: A synthetic evidence provider MUST supply the not-yet-built sources needed for the
  T0→T9 lifecycle, so the demo runs with real checks. It is on in dev and demo. Every decision
  that read synthetic evidence MUST be labelled `synthetic` in its decision record and in the
  run's control results, which approvers and auditors see.
- **FR-026**: The engine MUST contain no terminal-specific values or branching (constitution I).
  Predicates are generic over the tables, columns, evidence references and values named in
  the specs.

### Key Entities

- **Evaluation request**: an expression, the check id (prerequisite, control or condition id),
  and the run it is for.
- **Evaluation result**: passed or not passed, the computed value, the reason, and the inputs
  read.
- **Evidence source**: a named source of facts (terminal records and artifacts, intake,
  trigger, run, timeline, tier, params, and the external sources). It answers with a value or
  "not available".
- **Predicate**: a named, catalogued check with typed parameters and a return type.
- **Resolved parameter set**: per run, each parameter's value and source (use case or
  guardrail), plus any rejected use-case values with their reasons.
- **Permission rule**: a terminal's allow, deny and tool-scope entries. Deny wins; default
  deny.
- **Policy decision**: an append-only record of one evaluation or authorization (rule or
  action, check id, inputs, result, value, reason, run, use case, time, and whether any input
  was synthetic).
- **Synthetic artifact set**: per terminal, artifacts that meet its controls, used by the stub
  agent until real agents exist.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the prerequisites and automated controls in the registered T0–T9 specs
  evaluate to passed, not passed, or not passed with "evidence not available", with no engine
  error.
- **SC-002**: With the synthetic artifacts and evidence, 100% of blocking prerequisites and
  controls pass across a full T0→T9 lifecycle.
- **SC-003**: For each automated control, at least one known-bad artifact makes it fail with a
  reason that names the failing element.
- **SC-004**: 100% of evaluations and authorizations leave exactly one decision record. 0
  records can be changed or deleted.
- **SC-009**: 100% of decisions that read synthetic evidence are labelled `synthetic`, and 0
  decisions that read only real evidence are.
- **SC-005**: Parameter resolution is correct for 100% of guardrails at each tier, for
  stricter, equal, looser and absent use-case values.
- **SC-006**: Authorization matches an expected allow and deny matrix for the T0–T9
  authorities, including the deny-wins, default-deny and out-of-scope cases, with 0 errors.
- **SC-007**: The feature 003 scenario tests (happy path, D-2, D-3, D-4, D-5, D-7, D-9) pass
  with the real engine.
- **SC-008**: Evaluating one automated control takes under 50 milliseconds at the 95th
  percentile, measured over all 98 T0–T9 rules, with compiled rules cached, against the test
  database.

## Assumptions

- Expressions and predicate signatures are already validated by feature 002 at registration,
  so evaluation-time errors are unexpected; failing closed covers them anyway.
- The use-case profile is stored in the ledger by feature 005. Until then, no profile values
  exist: parameters resolve to guardrail tier values, and profile-based checks report "evidence
  not available".
- Real providers for CI, red-team, telemetry, environments, change records, datasets, the
  template, releases, the portfolio and retirement come with features 009–012. They plug into
  the evidence-provider interface without changes to the engine.
- `run.age` is the time since the run opened. The demo time scale of feature 003 applies to
  timer values only, not to evidence.
- Callers of `authorize` (agent runtime, tool servers) arrive in 006 and 010. This feature
  provides and tests the decision, and wires the orchestrator's existing calls.
- Outcome conditions in specs (for example "escalate when assurance functions disagree", or
  "terminate when residual risk is unacceptable") are guidance for humans in this MVP, not
  automated triggers. Feature 003 escalates on limits and timers only.
