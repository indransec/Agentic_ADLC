# Tasks: Policy Engine

**Input**: Design documents from `specs/004-policy-engine/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: required. Constitution IX makes these test-first: predicates (a pass case and a
fail-with-reason case for each), parameter resolution, authorization and fail-closed
evaluation. Test tasks come first in each phase and must fail before their implementation.

**Organization**: phases follow the spec's user stories in priority order (US1–US5 P1, US6–US7
P2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to (US1–US7)

## Conventions used by every task

- Code lives in `src/adlc/policy/`, unit tests in `tests/unit/policy/`, and database tests in
  `tests/integration/policy/`. Database tests use the 003 template-database harness
  (`tests/support/orchestration.py`), extended so it can build a `CelPolicyEngine`.
- No terminal ids, event names, role names or route destinations in `src/adlc/policy/`
  (constitution I). Column names come from the arguments a spec passes, or from the column
  conventions written in contracts/predicates.md.
- `evaluate` never raises (FR-004). Every call writes one decision record (FR-019).

---

## Phase 1: Setup

- [X] T001 Add `synthetic_dir: Path | None` (`ADLC_SYNTHETIC_DIR`, default `data/synthetic`, `off` = disabled) and `accounts_file: Path | None` (optional for the orchestrator) to `OrchestratorSettings` in `src/adlc/config/settings.py`; tests first in `tests/unit/test_settings.py`; document both in `.env.example` and keep `tests/unit/test_env_example.py` passing
- [X] T002 [P] Write failing migration tests in `tests/integration/policy/test_migration_0004.py`:
  - `run.policy_decision` has every column in data-model.md, with `kind` in (`evaluate`, `authorize`) and `reason` NOT NULL with "up to 2,000 characters", plus the index `(run_id, decided_at, policy_decision_id)`.
  - `run.run_parameter_set` has `run_id` as PK and FK to `run.terminal_run`, and every other column in data-model.md.
  - Both tables refuse UPDATE, DELETE and TRUNCATE for every identity (SQLSTATE 42501).
  - The app role has exactly SELECT and INSERT on both.
  - A downgrade to 0003 and an upgrade again work.
- [X] T003 Write `db/migrations/versions/0004_policy.py` (reusing `run.reject_mutation()` from 0003) so T002 passes
- [X] T004 [P] Create the package skeleton `src/adlc/policy/__init__.py`, `src/adlc/policy/README.md` (a stub: the module map from plan.md) and `src/adlc/policy/predicates/__init__.py`; add `*/adlc/policy/*` to `CORE_MODULES` in `Makefile`; add `COPY data ./data` to `deploy/api.Dockerfile`; create `data/synthetic/README.md` explaining that this is demo data, labelled synthetic in every decision that reads it

**Checkpoint**: migration 0004 applies and reverts; settings load.

---

## Phase 2: Foundational (blocks every story)

### Tests first

- [X] T005 [P] Write failing tests in `tests/unit/policy/test_values.py`:
  - JSON values convert to and from CEL values (maps, lists, numbers, text, bool, null).
  - "Numeric" accepts numbers and number-like text (`"80"`, `" 0.02 "`) and refuses `"80%"`.
  - "Truthy" accepts `true`, `"true"`, `"yes"` and `"1"`, case-insensitive.
  - "Open row" means `status` = `open`, or a `closed` column that is empty.
  - Durations convert from TDS strings (`7d`) and Python timedeltas to CEL durations; `window_end` stays text.
  - `NOT_AVAILABLE` is a distinct sentinel.
- [X] T006 [P] Write failing tests in `tests/unit/policy/test_compiler.py`:
  - A compiled program is cached by expression text: the same object is returned twice.
  - The referenced roots of each expression in the real T0–T9 specs are reported (`T1`, `param`, `intake`, `run`, …), using `adlc.spec_toolkit.expressions`.
  - A parse error is returned as an error value, not raised.
- [X] T007 [P] Write failing tests in `tests/unit/policy/test_engine_fail_closed.py`, using an in-memory evidence provider and a no-op decision sink. Each case gives `passed=False` with the exact reason prefix in contracts/policy-engine.md step 5:
  - evidence not available;
  - `rule is false`;
  - `rule did not return true/false`;
  - `evaluation error`;
  - an unknown function name;
  - `evaluation too slow` (with a fake clock showing more than 1 s);
  - `evidence too large` (a table over 10,000 rows, or text over 100,000 characters);
  - a missing member of an available source (`T0.risk_classification.tier` when T0 exists without that artifact) gives `evidence not available: T0.risk_classification`, not `evaluation error` (contracts/policy-engine.md step 2).

  `evaluate` never raises for any input, including a hypothesis test over random expression text.

### Implementation

- [X] T008 [P] Implement `src/adlc/policy/values.py` (T005)
- [X] T009 [P] Implement `src/adlc/policy/compiler.py`: a program cache keyed by expression, referenced roots via `adlc.spec_toolkit.expressions`, and parse errors as values (T006)
- [X] T010 Implement the `EvidenceProvider` protocol, `Evidence(value, source, synthetic)`, `NOT_AVAILABLE`, `InMemoryEvidenceProvider` (for tests) and `CompositeEvidenceProvider(real, synthetic)` in `src/adlc/policy/evidence.py`. The composite prefers a real value and marks a synthetic one `synthetic=True`.
- [X] T011 Implement the decision sink protocol and `PolicyDecision` value in `src/adlc/policy/store.py`, plus a no-op sink for unit tests. The SQL sink comes in US4.
- [X] T012 Implement `CelPolicyEngine.evaluate` in `src/adlc/policy/engine.py`. The steps are those of contracts/policy-engine.md:
  1. compile;
  2. check references against the provider, following each full path;
  3. build the activation in `src/adlc/policy/activation.py`;
  4. evaluate with a per-call reason collector;
  5. map the result;
  6. apply the size and time limits (1 s, 10,000 rows, 100,000 characters);
  7. emit a decision to the sink inside `tracing.span("policy", "evaluate", ...)`.

  It gets an empty predicate registry for now. This makes T007 pass.

**Checkpoint**: an engine that fails closed on everything except true rules.

---

## Phase 3: User Story 1 – Prerequisites are checked at run open (P1) 🎯 MVP

**Goal**: prerequisites evaluate against real 003 records: earlier terminals, the intake, the trigger and the run.

**Independent test**: open T1 after a T0 pass with a risk classification and every T1 prerequisite passes. Without the classification, PRE-T1-02 fails with "evidence not available: T0.risk_classification…", and the run is blocked.

### Tests first

- [X] T013 [P] [US1] Write failing integration tests in `tests/integration/policy/test_evidence_provider.py` for `SqlEvidenceProvider`:
  - `T<n>` comes from the latest closed run of the use case, with members `status`, `signed_by`, `closed_at`, `run_version`, `waivers`, `bound_to` (the spec's `ledger.bound_to` resolved), each artifact as rows, and emitted values from the ledger record (FR-008).
  - The run's own terminal comes from the open run, with `status` = `open`.
  - A terminal with no closed run is `NOT_AVAILABLE`.
  - After a rework, run 2's record is read (US1/AC4).
  - `intake` has `free_text`, `business_owner` and `title`; `trigger` has `event_id`, `severity` and `evidence`; `run` has `rework_count`, `age`, `now`, `usecase_id`, `run_version`, `risk_tier` and `mode`.
  - `timeline` and `tier` come from the pinned spec for the use case tier (`medium` when there is none yet).
  - Later sources are `NOT_AVAILABLE`.
  - US1/AC2: the reason names the missing member path.
  - A duration comparison as the specs write it (`run.age > timeline.escalate_after`) evaluates correctly (FR-011).
- [X] T014 [P] [US1] Write failing tests for the record predicates in `tests/unit/policy/predicates/test_records.py`, a pass case and a fail-with-reason case each, per contracts/predicates.md:
  - `evidence_exists`, `is_signed`, `is_frozen`, `is_live`, `is_provisioned`, `is_pinned`;
  - `in_directory`, `approved_by`;
  - `all_statuses_in`, `no_waiver_expiring_before`, `no_expired_waivers`, `waiver_expiring_within`.
- [X] T015 [P] [US1] Write failing integration tests in `tests/integration/policy/test_prerequisites.py`, using the real engine through the 003 harness:
  - US1/AC1: T1 prerequisites pass after a T0 pass.
  - US1/AC2: with the classification missing, the run is blocked and the reason names the evidence.
  - US1/AC3: a warn prerequisite is recorded, and the run proceeds.

### Implementation

- [X] T016 [US1] Implement `SqlEvidenceProvider` in `src/adlc/policy/evidence.py`, with its SQL in `src/adlc/policy/store.py` (full literal SQL, no f-strings), so T013 passes
- [X] T017 [P] [US1] Implement the `Directory` protocol, `AccountFileDirectory` (reusing `adlc.identity.accounts`) and `UnavailableDirectory` in `src/adlc/policy/directory.py`
- [X] T018 [US1] Implement `src/adlc/policy/predicates/records.py` and the registry in `src/adlc/policy/predicates/__init__.py`. Predicates receive a call context (evidence provider, run context, reason collector). The registry's `check_catalogue(predicates.yaml)` reports missing and extra names and arities. This makes T014 and T015 pass.

**Checkpoint**: prerequisites are real.

---

## Phase 4: User Story 2 – Automated controls are enforced on every build attempt (P1)

**Goal**: all 60 predicates; controls over artifacts and evidence; blocking versus advisory.

**Independent test**: good T1 artifacts pass every blocking control. A KPI with a non-numeric baseline fails CTL-T1-02, and the reason names the table, the row and the column.

### Tests first (one module per predicate group: pass case and fail-with-reason case each)

- [X] T019 [P] [US2] Write failing tests in `tests/unit/policy/predicates/test_tables.py`:
  - `all_rows_in`, `all_rows_have`, `all_rows_numeric`, `all_rows_true`, `all_rows_match`;
  - `column_mean`, `column_min`, `column_max` (an error on an empty table or non-numeric values);
  - `no_open_rows`;
  - `all_required_artifacts_present` (mandatory artifacts, plus conditional ones whose `when` holds, each evaluated as its own decision);
  - every "every row" check fails on an empty table with the reason `table is empty`;
  - no predicate changes its inputs: the tables are deep-equal before and after each call (FR-005).
- [X] T020 [P] [US2] Write failing tests in `tests/unit/policy/predicates/test_design.py` for `every_req_mapped`, `every_req_traced`, `all_tools_registered_or_flagged`, `token_budget_within_nfr`, `data_classes_within`, `hitl_covered`, `scan_clean`, `permissions_subset` and `any_design_deviation`
- [X] T021 [P] [US2] Write failing tests in `tests/unit/policy/predicates/test_evaluation.py` for `all_metrics_meet_thresholds` (each operator), `no_critical_threshold_missed`, `cost_within_budget`, `latency_within_nfr`, `judge_disputed` (with and without a `disputed` column), `scenario_passed`, `no_unmitigated_critical`, `assurance_disagreement` and `unacceptable_residual_risk`
- [X] T022 [P] [US2] Write failing tests in `tests/unit/policy/predicates/test_operations.py` for `alerts_cover`, `go_no_go_disputed`, `within_window`, `hash_matches`, `within_baseline_tolerance`, `no_breach_in_stage`, `rollback_failed`, `open_incident`, `exceeds_threshold`, `below_nfr`, `below_baseline`, `above_budget_for`, `kpi_below_target_for`, `all_monitors_reporting`, `regression_within_baseline` and `repeated_sev1`
- [X] T023 [P] [US2] Write failing tests in `tests/unit/policy/predicates/test_change.py` for `reentry_consistent`, `class_at_least_if`, `classification_disputed` and `has_change_class`, using the real change class catalogue
- [X] T024 [P] [US2] Write a failing test in `tests/unit/policy/test_catalogue_binding.py`: the registry equals `predicates.yaml` exactly (names and arities), and a missing or extra predicate makes `check_catalogue` fail with the list (FR-002)
- [X] T025 [P] [US2] Write failing integration tests in `tests/integration/policy/test_controls.py`:
  - US2/AC1: good artifacts pass.
  - US2/AC2: a bad cell fails with the table, column and row named.
  - US2/AC3: an advisory failure is recorded and does not block.
  - US2/AC5: a control needing `redteam` with no provider fails "evidence not available: redteam".

### Implementation

- [X] T026 [P] [US2] Implement `src/adlc/policy/predicates/tables.py` (T019)
- [X] T027 [P] [US2] Implement `src/adlc/policy/predicates/design.py` (T020)
- [X] T028 [P] [US2] Implement `src/adlc/policy/predicates/evaluation.py` (T021)
- [X] T029 [P] [US2] Implement `src/adlc/policy/predicates/operations.py` (T022)
- [X] T030 [P] [US2] Implement `src/adlc/policy/predicates/change.py` (T023)
- [X] T031 [US2] Register all groups in `src/adlc/policy/predicates/__init__.py`, and run `check_catalogue` when the engine is built (T024, T025)

**Checkpoint**: every catalogued predicate works, with reasons.

---

## Phase 5: User Story 3 – Parameters resolve within enterprise guardrails (P1)

**Goal**: `param.*` resolved per SA §5.4 and FR-012 to FR-014, frozen per run.

**Independent test**: for a `max` guardrail with a 0.02 tier value, 0.01 is used; 0.05 is rejected (0.02 used, with the rejection recorded); with no value, 0.02 is used.

### Tests first

- [X] T032 [P] [US3] Write failing unit tests in `tests/unit/policy/test_parameters.py` for `resolve(guardrails, tier, profile_values)`:
  - for each of the 9 real guardrails in `adlc-specs/shared/guardrails.yaml`, at each tier, stricter, equal, looser and absent values (stricter-or-equal applies to all, FR-013);
  - a non-numeric profile value is rejected;
  - a missing tier value leaves the parameter unresolved;
  - no tier uses `medium`;
  - a hypothesis property: a resolved value is never looser than its tier value.
- [X] T033 [P] [US3] Write failing integration tests in `tests/integration/policy/test_parameter_set.py`:
  - the set is written when the run opens (its first policy call) and read back unchanged by later checks of the run;
  - a rework run resolves its own set;
  - rejected values are stored in `rejected`;
  - `param.<unresolved>` gives "evidence not available: param.<name>";
  - US2/AC4: a control using `param.*` (CTL-T1-05, autonomy level at most the maximum) reads the resolved value for the use case's tier.

### Implementation

- [X] T034 [US3] Implement `src/adlc/policy/parameters.py` (pure) and the `ProfileSource` protocol with `NoProfile` (until feature 005) (T032)
- [X] T035 [US3] Freeze the set: on a run's first evaluation, resolve and insert into `run.run_parameter_set` (`ON CONFLICT DO NOTHING`), then read back. Cache per run in the engine. Provide `param` to the activation in `src/adlc/policy/engine.py` and `src/adlc/policy/store.py` (T033).

**Checkpoint**: controls compare against the right limits.

---

## Phase 6: User Story 4 – Every decision is recorded and explainable (P1)

**Goal**: one append-only decision record per call, with inputs, synthetic flag and timing.

**Independent test**: after T1 runs, there is one decision per prerequisite and per control attempt, with inputs and reasons; an UPDATE is refused.

### Tests first

- [X] T036 [P] [US4] Write failing integration tests in `tests/integration/policy/test_decision_log.py`:
  - one row per evaluate and authorize call, carrying `kind`, `run_id`, `usecase_id`, `terminal_id`, `check_id`, `rule`, `passed`, `value`, `reason` ("up to 2,000 characters"), `inputs`, `synthetic`, `fail_safe`, `duration_ms` and `decided_at`;
  - tables are stored as `{ref, rows, content_hash}`, never the rows themselves;
  - rows are written in their own transaction, so they remain when the caller rolls back (FR-020);
  - rows read back in order per run (FR-021);
  - SC-009: a decision is `synthetic` exactly when an input came from the synthetic provider.

### Implementation

- [X] T037 [US4] Implement `SqlDecisionSink` in `src/adlc/policy/store.py` (own short transaction per record; reasons truncated to 2,000 characters) and add the input recorder to `src/adlc/policy/activation.py`, which records what each evaluation read and whether it was synthetic (T036)

**Checkpoint**: an audit trail exists.

---

## Phase 7: User Story 5 – The running platform enforces real rules (P1)

**Goal**: the orchestrator uses `CelPolicyEngine`; the stub agent uses synthetic artifacts; synthetic evidence is labelled.

**Independent test**: the 003 scenario suite passes with the real engine. A bad synthetic artifact makes the run retry and then escalate.

### Tests first

- [X] T038 [P] [US5] Write a failing integration test in `tests/integration/policy/test_all_rules.py`. With the synthetic data, all 98 T0–T9 prerequisites and controls are evaluated for a walked lifecycle:
  - SC-001: none gives an evaluation error;
  - SC-002: every blocking one passes;
  - SC-008: the p95 time per control is printed and is under 50 ms with a warm program cache;
  - SC-003: for each blocking control, a change to the synthetic artifacts or evidence makes it fail, and the reason names the failing element (table and row, or evidence path).
- [X] T039 [P] [US5] Write failing tests in `tests/unit/policy/test_synthetic.py`:
  - `SyntheticEvidenceProvider` reads `data/synthetic/evidence.yaml`;
  - the stub agent artifact loader reads `data/synthetic/artifacts/T<n>.yaml` and falls back to placeholders when a file is missing;
  - hashes are consistent across sources (the synthetic T3 package hash equals `env.test.deployed_hash`, `env.prod.deployed_hash` and `release.package_sha256`);
  - `ADLC_SYNTHETIC_DIR=off` disables both.
- [X] T040 [P] [US5] Write a failing test in `tests/integration/policy/test_orchestrator_wiring.py`:
  - the harness, built with `CelPolicyEngine`, passes T0→T8;
  - each `control_results` entry carries `synthetic`;
  - a scripted bad artifact (a KPI baseline `"n/a"`) makes T1 retry three times and escalate with `retry_limit`, with the reason in the control results (US5/AC3).

### Implementation

- [X] T041 [US5] Write `data/synthetic/evidence.yaml` and `data/synthetic/artifacts/T0.yaml` … `T9.yaml`, with values that satisfy every blocking control and prerequisite of the registered specs (T038)
- [X] T042 [US5] Implement `src/adlc/policy/synthetic.py` (`SyntheticEvidenceProvider`, `load_synthetic_artifacts`) (T039)
- [X] T043 [US5] Make `StubAgent` in `src/adlc/orchestration/stubs.py` start from the synthetic artifacts when they are given (scripts still override). Add `synthetic: bool = False` to `EvalResult` in `src/adlc/orchestration/interfaces.py`, and copy it into `control_results` in `src/adlc/orchestration/engine.py`. Change the agent and reviewer actor ids to `agent:<run_id>` and `reviewer:<run_id>` (FR-016), updating any 003 test that asserts the old form.
- [X] T044 [US5] Add `build_policy_engine(engine, registry, settings)` in `src/adlc/policy/__init__.py`. Use it in `src/adlc/orchestration/__main__.py` instead of `StubPolicy`. Mount the account file read-only into the orchestrator in `deploy/compose.yaml`. Let the 003 test harness (`tests/support/orchestration.py`) choose a real engine (default for scenarios) or `StubPolicy` (for tests that script policy answers) (T040).

**Checkpoint**: the platform runs real checks end to end.

---

## Phase 8: User Story 6 – Actions are authorized against the terminal's permissions (P2)

**Goal**: deny wins, then allow, then default deny; run scope; tool scopes.

**Independent test**: T1's agent on its own run may `write:T1.artifacts` and may not `write:ledger.T0`. On another run, it is refused as out of scope.

### Tests first

- [X] T045 [P] [US6] Write failing unit tests in `tests/unit/policy/test_authorization.py`:
  - the order of contracts/authorization.md (run scope, tool use, deny, allow, default);
  - `read:ledger.all` is read as `read:ledger.*`;
  - each refusal reason text;
  - hypothesis properties: deny always wins; no allow match means refused; another run means refused.
- [X] T046 [P] [US6] Write a failing test in `tests/integration/policy/test_authorize_matrix.py`: an expected allow and deny matrix over the real T0–T9 authorities (at least one allowed, one denied, one default-denied and one tool case per terminal) gives 0 errors (SC-006), and each call writes a decision row with `kind=authorize`.

### Implementation

- [X] T047 [US6] Implement `src/adlc/policy/authorization.py` (pure), plus `CelPolicyEngine.authorize` and `authorize_decision` in `src/adlc/policy/engine.py` (T045, T046)

**Checkpoint**: separation of duties is enforceable at run time.

---

## Phase 9: User Story 7 – Conditions on approvers and follow-on events (P2)

**Goal**: real answers for `plus:`, `external:` and `then_when:`, with fail-safe directions.

**Independent test**: an incident at `sev1` writes `T7.rollback` and one at `sev3` doesn't. A T3 design deviation requires the solution architect; no deviation, no architect.

### Tests first

- [X] T048 [P] [US7] Write failing tests in `tests/integration/policy/test_conditions.py`:
  - US7/AC1: the plus approver is required only when `any_design_deviation` holds.
  - The CAB is required when `tier.cab_required` holds (high and medium tiers) and not at low.
  - US7/AC2: the follow-on is written for `sev1` and not for `sev3`.
  - US7/AC3: an unevaluable condition answers "holds" for `plus:` and `external:` and "does not hold" for `then_when:`, with `fail_safe=true` and the reason prefixed `fail-safe:`.

### Implementation

- [X] T049 [US7] Implement the fail-safe step (contracts/policy-engine.md step 6) in `src/adlc/policy/engine.py`. Make sure `trigger.severity` reaches the activation from the event payload, and that the conditions the orchestrator passes carry their check-id prefixes (T048).

**Checkpoint**: all stories pass.

---

## Phase 10: Polish and cross-cutting

- [X] T050 [P] Extend `tests/unit/test_no_hardcoded_values.py` so `src/adlc/policy/` is checked for terminal ids, event names, role ids and route destination ids (the existing scans cover `src/adlc` already; add the destination scan for `policy/`)
- [X] T051 [P] Write `src/adlc/policy/README.md` (how evaluate works, the namespaces, failing closed, synthetic labelling, how 005 and 009–012 plug in providers) and update `tests/scenario/README.md` to say scenarios run with the real engine
- [X] T052 Run the scenario suite 10 times in a row with the real engine (quickstart §4) and record the result
- [X] T053 Run `make check`, and fix any failure, including the 80% core coverage gate that now includes `policy/`
- [X] T054 Run the live-stack check (quickstart §5): run `make up` and `scripts.demo_drive`, list `run.policy_decision`, and confirm the synthetic labels for T3 onward. Then check that the `adlc.policy.evaluate` spans reach Jaeger (`/api/v3/operations?service=adlc-orchestrator`).

---

## Dependencies and execution order

- **Phase 1 → Phase 2 → stories.** Phase 2 blocks every story.
- **US1** provides the SQL evidence provider and the registry, so US2–US7 depend on it.
- **US2 and US3** can run in parallel after US1. US2/AC4 (controls using parameters) is tested in US3's T033.
- **US4** can run once US1 is done.
- **US5** needs US1–US4: the wiring requires all predicates, parameters and the decision log.
- **US6 and US7** need only US1 and Phase 2. They can run in parallel with US2–US4, before US5.
- **Phase 10** is last.

## Parallel examples

- **Phase 2**: T005, T006 and T007 together; then T008 and T009 together.
- **US2**: T019–T025 together; then T026–T030 together (one file each).
- **US6 and US7**: T045, T046 and T048 together.

## Implementation strategy

1. **MVP**: Phases 1–3. Prerequisites are real and fail closed.
2. **Controls and limits**: Phases 4–6 cover all predicates, parameters and the audit trail.
3. **Platform**: Phase 7 switches the orchestrator to the real engine.
4. **Remaining stories**: Phases 8–9, authorize and conditions.
5. Run `make check` and commit at each checkpoint.

---

## Phase 11: Convergence

- [X] T055 Change the orchestrator's agent and reviewer actor ids from `<kind>:<terminal>` to `<kind>:<run_id>` in `src/adlc/orchestration/engine.py`, and assert in a test that an agent can be authorized for its own run under its recorded id, per FR-016 (missing)
- [X] T056 Record in `specs/004-policy-engine/plan.md` that wiring lives in `src/adlc/policy/factory.py` (not `__init__.py`, to avoid an import cycle with the predicate modules), that `scripts/make_synthetic.py` generates `data/synthetic/`, and that the authorization matrix runs as a unit test, per plan: project structure (unrequested)
