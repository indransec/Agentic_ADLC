# Feature Specification: Terminal Spec Toolkit

**Feature Branch**: `002-terminal-spec-toolkit`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "Feature 002 terminal-spec-toolkit. Build the spec toolkit: the machine-readable terminal spec standard, validation (L1–L5) and registration of ADLC terminal specs and shared catalogues, and conversion of the current T0–T9 terminal specs so they pass validation."

## Clarifications

### Session 2026-11-10

- Q: What is the L5 version-bump baseline? → A: The file on `main` during validation (local and CI); the latest registered version during registration.
- Q: Which tier-dependent values move to guardrails? → A: Numeric safety and assurance limits only (tighten-only); process-depth settings stay in `controls.tiering`.
- Q: What status do the converted specs get? → A: `active`, with TDS §15 proposed defaults flagged in the conversion record and guardrails.
- Q: How do validated specs reach the dev and demo registries? → A: An operator runs a registration command on the host after pulling `main`, and the environment start registers automatically after migrations. On merge, CI validates and registers into a throwaway data store to prove registration works.
- Q: What does "earlier terminal" mean for V-02 evidence references? → A: The referenced terminal can reach the referencing terminal through the event and route graph built from all specs; no terminal order is assumed.

**Source sections**: build plan §6 (row 002), §9; SA §5.1–§5.5, §6.2, §9 (separation of duties at spec release), §10 (`spec` schema), §20 (open decisions), Annex A; TDS §2–§14, Annex B (B.1–B.5), Annex C (C.1, C.2); constitution I, II, III, V, VI, VII, XII, XIII.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Validate the spec folder in one command (Priority: P1)

A spec author (ADLC CoE member or terminal owner) runs one validation command over the
`adlc-specs/` folder and gets every problem at once. Each finding names the file, the location
inside the file, the rule id and the level, from L1 to L5:

- **L1** parse.
- **L2** schema: the Annex B dictionary, with unknown fields refused.
- **L3** single-spec rules.
- **L4** cross-spec graph and references, across all terminal specs and shared catalogues.
- **L5** version-bump rules.

**Why this priority**: every other part of this feature, and every later feature that reads
specs, depends on validation catching broken specs before merge (SA §5.5, constitution I).

**Independent Test**: run validation on a folder of known-good fixtures (zero findings) and on
a set of known-bad fixtures, one per rule. Each bad fixture is reported with its rule id and
location.

**Acceptance Scenarios**:

1. **Given** a spec folder with no problems, **When** validation runs, **Then** it reports zero
   findings and exits successfully.
2. **Given** a terminal spec with an unknown field, a wrong type and a missing required field,
   **When** validation runs, **Then** all three are reported at L2, each with file, field path
   and rule id, and validation exits unsuccessfully.
3. **Given** problems in several files at several levels, **When** validation runs, **Then**
   all problems are reported in one run. Problems that cannot be checked because the file
   failed to parse are reported as skipped, not silently dropped.
4. **Given** a trigger event that no terminal emits and that is not an external event in the
   catalogue, **When** validation runs, **Then** it is reported at L4 under V-03.
5. **Given** a terminal spec whose content changed but whose version did not, compared with
   the baseline version, **When** validation runs, **Then** it is reported at L5.
6. **Given** a request for machine-readable output, **When** validation runs, **Then**
   findings are produced in a structured form that CI and editors can consume.

---

### User Story 2 - Shared catalogues as the single source of names and limits (Priority: P1)

The CoE maintains every shared catalogue as a versioned file in `adlc-specs/shared/`, validated
together with the terminal specs (SA §5.1, §5.3):

- roles (from 001), risk tiers, the event catalogue (internal patterns and external events)
- root causes, change classes, data classes, model tiers
- the MCP server registry with scopes, permission verbs
- the predicate catalogue, the metric catalogue, and guardrails per risk tier

Terminal specs may only use names that these catalogues define.

**Why this priority**: catalogues turn free text into checkable references. Without them, L4
cannot work, and later features (policy engine 004, context packs 006, dashboard 013) have no
authoritative vocabulary.

**Independent Test**: validate the catalogues on their own; then remove one role, predicate,
metric and MCP scope that the terminal specs use, and confirm each dangling reference is
reported with the referencing file and location.

**Acceptance Scenarios**:

1. **Given** the shared catalogues, **When** validation runs, **Then** every catalogue is
   checked for its own structure (unique ids, required fields, naming rules).
2. **Given** a terminal spec that references a role, event, root cause, change class, data
   class, model tier, MCP server or scope, permission verb, predicate, metric or guardrail
   parameter that is not in the catalogues, **When** validation runs, **Then** each unknown
   name is reported at L4 with the catalogue it should come from.
3. **Given** a predicate used with the wrong number or kind of arguments, **When** validation
   runs, **Then** it is reported against the predicate's declared signature.
4. **Given** a guardrail limit marked tighten-only, **When** the guardrails file defines tier
   values that loosen it from a stricter tier to a riskier one (for example, high allows more
   injection success than low), **Then** validation reports the inconsistency.

---

### User Story 3 - Converted T0–T9 specs that pass validation (Priority: P1)

The CoE gets `adlc-specs/terminals/T0.yaml` … `T9.yaml`, converted from TDS §4–§13 so that they
pass L1–L5 with zero findings, keep the behaviour the TDS describes, and apply the SA §20
decisions:

- **Free-text conditions and rules** become expressions, or calls to named predicates from the
  predicate catalogue (SA §5.5).
- **Applicability**: every artifact (and every metric requirement, where one exists) carries
  `mandatory`, `conditional` with a predicate, or `optional` (SA §5.2). Artifacts the TDS
  marks `required: on_retire` become conditional on a predicate.
- **Guardrails**: safety and assurance numeric limits move out of terminal specs into the
  guardrails file, and specs reference them by parameter name (constitution II; SA §5.4).
- **Clarification limits**: every timeline has `clarification_sla` and
  `max_clarification_rounds` (SA §6.2).
- **Naming**: SA Annex A alignment is applied. `max_injection_success` becomes
  `injection_success_max`, metrics get `_rate` and unit suffixes, numeric artifact columns get
  unit suffixes, and T8 event names follow `T8.event.<name>`.
- **Free-text extras**: annotations outside the Annex B dictionary are either mapped to
  dictionary fields or moved into documented optional fields. Examples are T3
  `sign_off.plus` as free text, T6 `exception.example`, T9 `terminate.meaning`, and T7
  `expected_duration: 1d+3d_hypercare`.

**Why this priority**: the orchestrator (003) needs real, valid specs to run T0–T9 with stub
agents by the end of November (build plan §7).

**Independent Test**: validate `adlc-specs/` (zero findings), then compare each converted spec
with its TDS section through a conversion record. Every trigger, prerequisite, control,
artifact, route and timer in the TDS is present in the converted spec, or listed with a
reason in the record.

**Acceptance Scenarios**:

1. **Given** the ten converted specs and the catalogues, **When** validation runs, **Then** it
   reports zero findings.
2. **Given** a TDS terminal section and its converted spec, **When** the conversion record is
   reviewed, **Then** every TDS element is either present unchanged, present converted (with
   the TDS text kept as a description), or listed as removed or moved with a reason.
3. **Given** any converted spec, **When** its controls and prerequisites are inspected,
   **Then** none has a free-text rule or condition; each is an expression or a named
   predicate call.
4. **Given** the guardrails file, **When** a converted spec needs a tier-dependent safety
   limit, **Then** the spec references the guardrail parameter and holds no number for it.

---

### User Story 4 - Register specs into the platform registry (Priority: P1)

A platform engineer registers the validated specs into the platform data store:

- One registry entry per terminal version, holding the spec content, its normalised form and
  its content hash (Annex C.2 SPEC_REGISTRY).
- Projection rows that later features read without parsing YAML: trigger subscriptions,
  outcome routes (including root-cause routes and T8 event routes), and timeline policies per
  risk tier.

Everything is written in one transaction. The previous version of a terminal is marked
deprecated, and a registered version is never changed (SA §5.5, §10).

**Why this priority**: SA §5.5 makes registration the only way specs reach run time, and the
orchestrator (003) routes from the projections.

**Independent Test**: register the converted specs on an empty data store, then query the
projections:

- `usecase.submitted` opens T0.
- T4 rework with root cause `implementation` routes to T3.
- `T8.event.drift` routes to T9.
- T3's timeline for risk tier `medium` has expected duration 10 days.

**Acceptance Scenarios**:

1. **Given** an empty registry and valid specs, **When** registration runs, **Then** one
   active registry entry per terminal and all projection rows exist. All of them are written
   or none are.
2. **Given** specs already registered unchanged, **When** registration runs again, **Then**
   nothing changes and it reports "no changes".
3. **Given** a spec whose content changed without a version bump, **When** registration runs,
   **Then** it is refused with a message naming the terminal, and nothing is written.
4. **Given** a spec with a bumped version, **When** registration runs, **Then** the new
   version is active, the previous version of that terminal is deprecated, and the previous
   version's entry and projections are otherwise unchanged.
5. **Given** a registered version, **When** any data store identity tries to update or delete
   its registry entry, **Then** the change is refused. A status change from `active` to
   `deprecated` or `retired` is the only permitted change, and only through registration.
6. **Given** validation findings in the folder, **When** registration is attempted, **Then**
   it is refused before anything is written.

---

### User Story 5 - Route lookups for the orchestrator (Priority: P2)

The orchestrator (feature 003) and other platform modules look up routing data from the
active registered versions through one read interface:

- which terminals an event opens
- where an outcome routes, including by root cause
- where an operational event routes
- the timeline for a risk tier

**Why this priority**: it is what 003 consumes, but 003 can start from the projection tables
directly. The read interface prevents every caller from writing its own queries.

**Independent Test**: after registration, call each lookup for the cases in US4's
independent test and get the expected answers. Call them for an unknown event or root cause
and get an explicit "no route" answer, not an error or a guess.

**Acceptance Scenarios**:

1. **Given** registered specs, **When** a caller asks which terminals `T2.pass` opens,
   **Then** the answer is T3.
2. **Given** registered specs, **When** a caller asks where T4 `rework` with root cause
   `requirement` routes, **Then** the answer is T1.
3. **Given** an event no active spec subscribes to, **When** a caller asks which terminals it
   opens, **Then** the answer is an empty result.
4. **Given** a terminal with two registered versions, **When** a caller asks for routes,
   **Then** only the active version is used, unless the caller names a specific version.

---

### User Story 6 - Editor support and CI gate (Priority: P2)

A spec author's editor validates terminal YAML against the published schema while they type.
Spec validation is part of the shared checks, so an invalid spec cannot be merged (build plan
§9 "Spec tests").

**Why this priority**: it shortens the author's feedback loop and protects `main`. The
validation command (US1) already gives the same result, just later.

**Independent Test**: open a terminal spec in an editor with schema support and see an unknown
field flagged. Break a spec, run the shared check command, and see it fail at the spec
validation step.

**Acceptance Scenarios**:

1. **Given** the published schema file, **When** an editor with YAML schema support opens a
   terminal spec, **Then** structural errors (L2) are shown in the editor.
2. **Given** an invalid spec on a branch, **When** the shared checks run locally or in CI,
   **Then** the spec validation step fails and names the problems.

---

### Edge Cases

- A YAML file that does not parse: reported at L1 with line and column; its L2–L5 checks are
  reported as skipped; other files are still validated.
- Two terminal specs claim the same terminal id: V-01 across the folder.
- A file in `adlc-specs/terminals/` whose name does not match its `metadata.id`: reported.
- Cyclic routes are allowed, because rework loops are intended; routes that can never reach a
  terminating outcome are not.
- A rework root cause routes to a terminal that does not subscribe to the matching
  `T<n>.rework.<cause>` event: reported at L4.
- A special route destination such as `owning_terminal` (T6 rework on missing evidence),
  `human_completion`, a role group, or a template such as T9's
  `${change_impact_assessment.reentry_terminal}`: must be a value declared in a catalogue of
  special destinations, otherwise reported.
- An evidence reference to a non-terminal source such as `intake.`, `env.`, `change.`,
  `template.`, `dataset.` or `trigger.`: must name a source declared in the catalogue.
- An evidence reference to a terminal that cannot reach the referencing terminal through the
  event and route graph (for example, T2 requiring T5 evidence while no route leads from T5 to
  T2): reported under V-02. References made reachable by re-entry or rework routes (for
  example, T9 → T2 reading T8 evidence) are valid.
- A predicate in the catalogue that no spec uses: allowed (reported as information, not a
  failure).
- Registration interrupted midway (process stopped): nothing is written. A rerun registers
  everything.
- Two registrations run at the same time: one waits for or refuses the other; the registry is
  never left with two active versions of one terminal.
- A spec version that goes down (for example 1.2.0 to 1.1.0): reported at L5.
- Retiring a version that a use case has pinned: refused (SA §5.5). In this feature the pin
  table may be empty; the rule exists for when 003 writes pins.

## Requirements *(mandatory)*

### Functional Requirements

**Spec standard**

- **FR-001**: The terminal spec standard MUST be published as a machine-readable schema in
  `adlc-specs/schema/` that implements the TDS Annex B dictionary (schema version 1.0.0), plus
  these additions: applicability, clarification timeline fields, guardrail references, and
  documented optional annotation fields. Unknown fields MUST be refused.
- **FR-002**: Every addition to Annex B MUST be listed in a dictionary change note in
  `adlc-specs/schema/` with its reason, so the TDS can be updated to match.
- **FR-003**: Expressions in specs MUST follow one documented grammar (TDS Annex B.3, with any
  changes recorded in the change note). Named predicates MUST be called by name with
  arguments that match their catalogue signature.

**Shared catalogues**

- **FR-004**: `adlc-specs/shared/` MUST hold one versioned file per catalogue:
  - roles (from 001)
  - risk tiers
  - events (internal patterns per Annex A.3, and external events such as
    `usecase.submitted`, `change.requested` and `lifecycle.review_due`)
  - root causes, change classes, data classes, model tiers
  - MCP servers with their scopes
  - permission verbs
  - evidence sources (non-terminal reference prefixes)
  - route destinations (special non-terminal destinations)
  - predicates (name, parameters, description)
  - metrics (name, class, unit, direction, measurement method; SA §5.3)
  - guardrails: per risk tier floors, ceilings and defaults, each marked tighten-only where
    it is a safety or assurance limit (SA §5.1, §5.4)
- **FR-005**: Each catalogue MUST be validated for unique ids, required fields and Annex A
  naming.
- **FR-006**: Permissions MUST be declared with a duty group (for example build, evaluate,
  deploy) in the permission catalogue, so that separation of duties can be checked from data,
  not from terminal ids (constitution I, IV; SA §9).

**Validation (L1–L5)**

- **FR-007**: One command MUST validate the whole `adlc-specs/` folder and report every
  finding with level (L1–L5), rule id, file, location within the file (field path, and line
  where available) and message. It MUST exit unsuccessfully if any finding has severity
  error.
- **FR-008**: Validation MUST implement V-01 to V-10 (TDS Annex B.5) as written, plus at least
  these rules:
  - expressions parse
  - every name used in an expression or predicate call is defined (predicate, metric, guardrail
    parameter, run variable, evidence reference)
  - every artifact has applicability, and conditional applicability names a predicate
  - every timeline has clarification limits
  - every status right conforms to constitution III: only humans set pass, exception and
    terminate; only the orchestrator sets escalate; the reviewer only recommends
  - one terminal's allowed permissions never span two duty groups (separation of duties)
  - rework root-cause routes target terminals that subscribe to the matching rework event
  - every rework root cause and change class comes from its catalogue
  - spec ids, file names and names follow SA Annex A patterns
  - guardrail tighten-only consistency across tiers
  - L5 version rules: a content change needs a version bump, versions never go down, a
    removed field or changed route needs a major or minor bump per the rule table in the
    plan
- **FR-008a**: V-02 MUST treat a referenced terminal as earlier when it can reach the
  referencing terminal through the event and route graph built from all registered or
  validated specs: trigger subscriptions, outcome routes, root-cause routes, event routes and
  change-class re-entries. No terminal order may be assumed from ids (constitution I).
- **FR-009**: Each rule MUST have a stable id and be documented with its level, severity and
  one example finding.
- **FR-010**: Validation MUST offer a structured output format for CI and editor tooling in
  addition to the human-readable report.
- **FR-011**: L5 MUST compare each terminal spec with two baselines:
  - **During validation** (locally and in CI): the same file on the `main` branch, so no data
    store is needed. A new file has no baseline and passes L5.
  - **During registration**: the latest version of that terminal in the target registry, so
    no environment gets changed content under an already-registered version.

**Conversion of T0–T9**

- **FR-012**: `adlc-specs/terminals/T0.yaml` … `T9.yaml` MUST exist, converted from TDS §4–§13,
  and MUST pass validation with zero findings.
- **FR-013**: Every free-text condition or rule in the TDS MUST be converted to an expression
  or a named predicate call. The original TDS wording MUST be kept as the item's
  `description`.
- **FR-014**: Numeric safety and assurance limits MUST live in the guardrails file as
  tier-specific, tighten-only values, and specs MUST reference them by parameter name. This
  covers injection and jailbreak success maxima, the judge agreement minimum, the unit
  coverage minimum, the minimum test scenarios and cases, and the RAI metric classes required
  per tier. Process-depth settings stay in each spec's `controls.tiering`: red-team mode,
  threat-model depth, architecture board review, adversarial depth, rollout stages, canary
  percentage, and soak and hypercare durations.
- **FR-015**: A conversion record in `adlc-specs/` MUST list, per terminal, every element that
  was renamed, converted, moved or removed, with the TDS location and the reason.
- **FR-016**: Every playbook and checklist that a spec references MUST exist at the stated
  version (V-10). Playbook files MAY be stubs carrying id, version, title and owner. Checklist
  files MUST carry every item id with its text.
- **FR-017**: The converted specs MUST have status `active`. Every numeric value that TDS §15
  lists as a proposed default MUST be marked "proposed default" in the conversion record and
  the guardrails file. Confirming or changing one later is a normal versioned spec change.

**Registry and projections**

- **FR-018**: Registration MUST refuse to run while validation reports any error, and MUST
  write nothing in that case.
- **FR-019**: Registration MUST write, in one transaction:
  - one registry entry per new terminal version (terminal id, version, status, original
    content, normalised content, content hash, trigger events, emitted events, registered
    time; Annex C.2)
  - projection rows for trigger subscriptions, outcome routes (status and root cause to
    destination, with requirements such as owner comment, and waiver recheck terminals),
    event routes, and timeline policies per risk tier
  - the playbook registry (id, version, path, content hash)
- **FR-020**: Registration MUST be idempotent: unchanged specs produce no writes. A changed
  spec without a version bump MUST be refused. Registering a new version MUST mark the
  previous active version of that terminal `deprecated` in the same transaction.
- **FR-021**: Registered entries and projection rows MUST be immutable for every data store
  identity, except for the registry status transitions active → deprecated → retired, which
  only registration (or retirement) may perform. Retiring a version that any use case has
  pinned MUST be refused (SA §5.5).
- **FR-022**: At any time there MUST be at most one active version per terminal.
- **FR-023**: The content hash MUST be computed from the normalised content, so that
  formatting-only changes (whitespace, key order, comments) do not create a new version.
- **FR-023a**: Registration MUST be run on the host of the target environment (`dev` or `demo`)
  by one documented command, against that environment's data store. Starting the environment
  MUST register the specs automatically after migrations, so a fresh environment always has
  the specs it was started with. The running platform services MUST only read the registry
  (SA §10).
- **FR-023b**: CI MUST, on every pull request and on `main`, validate the specs and register
  them into a throwaway data store, so a merge to `main` proves both validity and registrability.
  CI never writes to a `dev` or `demo` registry.

**Read interface**

- **FR-024**: A read interface MUST answer, from active versions (or a named version):
  - the terminals an event opens
  - the destination for a terminal outcome, optionally by root cause
  - the destination for an operational event
  - the timeline for a terminal and risk tier
  - the registry entry for a terminal and version

  An unknown key MUST return an explicit empty result.
- **FR-025**: The read interface MUST be the only way platform modules read spec data (no YAML
  parsing at run time), and MUST sit behind an interface so its storage can change
  (constitution VII).

**Editor and CI**

- **FR-026**: Terminal YAML files MUST declare the published schema so that editors with YAML
  schema support validate them.
- **FR-027**: Spec validation MUST be a named step in the shared checks from 001, and CI MUST
  run it.
- **FR-028**: Platform code delivered here MUST contain no terminal-specific branching or
  values (constitution I). The toolkit treats every terminal the same way, and any behaviour
  that differs by terminal comes from the specs or catalogues.

### Key Entities

- **Terminal spec**: one YAML file per terminal and version. Contains metadata, trigger,
  prerequisites, actors, authorities, playbooks, controls, evidence, outcome model, timeline,
  and for some terminals monitors, change classes and a retirement procedure (TDS Annex B,
  C.1).
- **Shared catalogue**: one versioned file of named entries (roles, events, predicates,
  metrics, guardrails, …) that specs reference by name.
- **Predicate**: a named, typed check with parameters. It is declared here and evaluated by
  the policy engine (004).
- **Metric**: a catalogue entry with class, unit, direction and measurement method (SA §5.3).
- **Guardrail**: a parameter with a value per risk tier and a tighten-only flag (SA §5.4).
- **Playbook / checklist**: a versioned file referenced by id and version. Checklists hold the
  reviewer's item ids and text.
- **Validation finding**: level, rule id, severity, file, location, message.
- **Registry entry**: terminal id, version, status (active, deprecated, retired), original and
  normalised content, content hash, trigger events, emitted events, registered time.
- **Projection rows**: trigger subscription (event → terminal version), outcome route
  (terminal version, status, root cause → destination, requirements, recheck terminals),
  event route (terminal version, event → destination, immediate actions, notify), timeline
  policy (terminal version, risk tier → durations and limits).
- **Conversion record**: per terminal, the list of TDS elements and what happened to each.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Validating the full `adlc-specs/` folder (10 terminal specs and all catalogues)
  completes in under 10 seconds and reports zero findings for the converted specs.
- **SC-002**: 100% of validation rules (V-01 to V-10 and every added rule) catch their negative
  fixture, with the correct rule id and location.
- **SC-003**: 100% of TDS triggers, prerequisites, controls, artifacts, routes and timers for
  T0–T9 are accounted for in the conversion record (present, converted, moved or removed with
  a reason).
- **SC-004**: Zero free-text rules or conditions remain in the converted specs.
- **SC-005**: Registering all ten specs on an empty data store completes in under 30 seconds.
  A repeat registration writes nothing, and an interrupted registration leaves no partial
  rows.
- **SC-006**: 100% of attempts to update or delete a registered spec version or projection row
  are refused, apart from the permitted status transitions.
- **SC-007**: The route lookups for every demo moment that needs routing data (D-3, D-4, D-5,
  D-7, D-9) return the expected answers from the registered specs.
- **SC-008**: A spec author sees an unknown-field error in the editor, and the shared check
  command fails on an invalid spec, in both cases within one save or one run.

## Assumptions

- Expression and predicate evaluation is feature 004. Here, expressions are only parsed and
  their names resolved.
- The use-case spec pin table (Annex C.2 USECASE_SPEC_PIN) is created here with the registry,
  because the "no retirement while pinned" rule needs it. Pins are written by the orchestrator
  (003).
- Per-terminal pinning is used for the MVP; spec bundles are post-MVP (SA §20).
- Projection tables beyond trigger, outcome route, event route and timeline are not built here
  (build plan §6 simplify-if-late). The normalised content in the registry carries everything
  else.
- The TDS remains the narrative source. The dictionary change note and the conversion record
  are the inputs for updating TDS Annex B and the terminal sections.
- Numeric values in the converted specs and guardrails are the TDS proposed defaults (TDS §15),
  unchanged unless Annex A naming requires a unit change, and flagged as proposed defaults
  (FR-017).
- Default clarification limits: `max_clarification_rounds: 2` (SA §6.2 proposal) and
  `clarification_sla` equal to the terminal's `reminder_after`, set per terminal in the spec.
- Registration uses the schema-owner identity (feature 001). The SA §5.5 "release job on
  merge" is realised as CI validation plus host-side registration (FR-023a, FR-023b), because
  hosted CI cannot reach the dev or demo data stores. SA §5.5 should be updated to match.
