---
description: "Task list for 002-terminal-spec-toolkit"
---

# Tasks: Terminal Spec Toolkit

**Input**: Design documents from `specs/002-terminal-spec-toolkit/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Required by constitution IX. Every validation rule gets a negative fixture first.
Routing data and registry immutability are test-first.

**Organization**: Grouped by user story. Stories run in dependency order: US2 (catalogues) →
US1 (validation) → US3 (conversion) → US4 (registration) → US5 (read interface) → US6 (editor
and CI). L4 rules need the catalogues, and registration needs validated specs.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: User story from spec.md (US1–US6)

---

## Phase 1: Setup

- [X] T001 Add dependencies with `uv add jsonschema networkx cel-python` and `uv add --dev types-networkx types-jsonschema`. Add a `[[tool.mypy.overrides]]` with `module = ["celpy", "celpy.*"]` and `ignore_missing_imports = true` (celpy only) to `pyproject.toml`, then run `uv lock`; confirm `make install lint typecheck` still pass
- [X] T002 [P] Create module skeleton `src/adlc/spec_toolkit/{__init__,cli,loader,schema,expressions,catalogues,graph,findings,normalise,projections,register,registry}.py` and `src/adlc/spec_toolkit/rules/{__init__,single_spec,cross_spec,versioning}.py` (empty typed stubs); replace `src/adlc/spec_toolkit/README.md` placeholder with module purpose
- [X] T003 [P] Add console script `adlc-spec = "adlc.spec_toolkit.cli:app"` to `pyproject.toml`
- [X] T004 [P] Create the fixture harness `tests/support/spec_fixtures.py`:
  - `build_bundle(tmp_path, patches)` copies the minimal valid bundle `tests/fixtures/specs/_valid/` into `tmp_path`, then applies patch operations from `tests/fixtures/specs/<rule-id>/patch.yaml` (`{file, op: set|delete|append|write_text, path, value}`).
  - `expected.yaml` beside each patch lists the expected `rule_id`, `file` and `path` substring.

---

## Phase 2: Foundational (blocking)

**⚠️ No story work starts before this phase is done.**

- [X] T005 [P] Write failing tests for `tests/unit/spec_toolkit/test_findings.py`:
  - A `Finding` has `rule_id`, `level` (`L1`–`L5`), `severity` (`error`|`warning`|`info`), `file`, `path` (JSON pointer), `line`, `column` and `message`.
  - The text reporter sorts by file and line and ends with the summary line `"<e> errors, <w> warnings, <i> info in <n> files (<t> s)"`.
  - The JSON reporter emits `{"summary": {...}, "findings": [...]}` per contracts/adlc-spec-cli.md.
  - `has_errors()` is true only when an `error` is present.
- [X] T006 [P] Implement `Finding`, `Severity` and `Level` plus the text and JSON reporters in `src/adlc/spec_toolkit/findings.py` so T005 passes
- [X] T007 [P] Write failing tests for `tests/unit/spec_toolkit/test_loader.py`:
  - Loading a folder yields a `SpecBundle` with terminals keyed by file, catalogues keyed by `catalogue` name, checklists, and playbooks with parsed front matter.
  - A YAML syntax error gives P-01 with line and column, and that file is marked `parse_failed`.
  - A missing catalogue file or a misnamed terminal file gives P-02.
  - `bundle.location(file, json_pointer)` returns the line and column of a node.
- [X] T008 Implement the loader in `src/adlc/spec_toolkit/loader.py` so T007 passes: ruamel.yaml round-trip loader, `CommentedMap.lc` location index, and front matter split on `---` for playbooks (research R-04)
- [X] T009 [P] Write failing tests for `tests/unit/spec_toolkit/test_normalise.py`:
  - Normalised JSON is identical for files that differ only in comments, key order and whitespace.
  - `content_hash` matches `^sha256:[0-9a-f]{64}$`.
  - A changed value changes the hash.
  - Playbook hashing uses the full file bytes (research R-09).
- [X] T010 [P] Implement `normalise(data) -> str` and `content_hash(...)` in `src/adlc/spec_toolkit/normalise.py` so T009 passes
- [X] T011 Write failing tests, then implement the rule registry in `src/adlc/spec_toolkit/rules/__init__.py`.
  - Tests go in `tests/unit/spec_toolkit/test_rule_registry.py`.
  - A `@rule(id, level, severity, summary)` decorator registers rules, and duplicate ids are refused.
  - `run_rules(bundle)` runs rules in level order and skips files with L1/L2 errors for L3+, emitting one `info` finding "skipped (earlier errors)" per skipped file and level.
- [X] T012 Write `tests/unit/spec_toolkit/test_rules_documented.py`: the set of rule ids in the registry equals the set of ids in the first column of `specs/002-terminal-spec-toolkit/contracts/validation-rules.md` (excluding R-* registration refusals)
- [X] T013 [P] Create the minimal valid fixture bundle `tests/fixtures/specs/_valid/`.
  - Two terminals, `terminals/T0.yaml` and `terminals/T1.yaml`, routing to each other.
  - The smallest catalogue files, one checklist each, and one playbook each.
  - Together they must pass every rule. The file is built incrementally as the rules land, and its final form is asserted in T034.

**Checkpoint**: load → findings → report works on an empty rule set.

---

## Phase 3: User Story 2 - Shared catalogues (Priority: P1)

**Goal**: every catalogue exists in `adlc-specs/shared/`, has a schema, and is validated on its own.

**Independent Test**: `adlc-spec validate` on the catalogues alone reports zero findings. Each catalogue negative fixture (S-02, V-18 for catalogue names, V-19) is caught.

### Tests for US2 (write first) ⚠️

- [X] T014 [P] [US2] Add negative fixtures for S-02 (missing `unit` on a metric; unknown field on a role), V-18 (guardrail named `max_injection_success`; metric ratio not ending `_rate`), V-19 (`injection_success_max` high > low) under `tests/fixtures/specs/S-02-*/`, `V-18-*/` and `V-19-*/`, plus `tests/unit/spec_toolkit/test_rule_fixtures.py`, which parametrises over every fixture folder and asserts the expected finding
- [X] T015 [P] [US2] Write `tests/unit/spec_toolkit/test_catalogue_views.py`. The typed views in `catalogues.py` expose:
  - role ids, risk tier ranks, event patterns and external events
  - root causes, change classes, data class ranks, model tiers
  - MCP server scopes, permission verbs and duty groups
  - evidence source fields, route destinations by kind
  - predicate signatures, metrics and guardrails

### Implementation for US2

- [X] T016 [P] [US2] Write the catalogue JSON Schemas in `adlc-specs/schema/catalogues/`, one per catalogue in contracts/spec-files.md (`roles`, `risk_tiers`, `events`, `root_causes`, `change_classes`, `data_classes`, `model_tiers`, `mcp_servers`, `permissions`, `evidence_sources`, `route_destinations`, `predicates`, `metrics`, `guardrails`).
  - Use draft 2020-12 with `additionalProperties: false`.
  - Top-level `catalogue` is a const of the file name and `version` is a quoted semver.
  - Ids are unique: enforce in code (V-01) because JSON Schema cannot express it.
- [X] T017 [US2] Update `adlc-specs/shared/roles.yaml` to the catalogue format (add `catalogue: roles`, `version: "1.0.0"`, keep `schema_version` out, keep the `roles` list). Keep `src/adlc/identity/catalogue.py` working, and run `tests/unit/test_role_catalogue.py`.
- [X] T018 [P] [US2] Write `adlc-specs/shared/risk_tiers.yaml` (`low` rank 1, `medium` rank 2, `high` rank 3; TDS §3), `root_causes.yaml` (the 11 values of TDS B.2 `root_cause`), `change_classes.yaml` (5 values of TDS B.2), `data_classes.yaml` (6 values of B.2 with rank order public < internal < synthetic_or_masked < confidential_masked < confidential < restricted, plus special `per_T2_prod_design` documented as a resolver) and `model_tiers.yaml` (`reasoning`, `coding`, `standard`)
- [X] T019 [P] [US2] Write `adlc-specs/shared/events.yaml`.
  - Patterns per Annex A.3: `T<n>.<status>`, `T<n>.rework.<root_cause>`, `T9.reentry.T<n>`, `T8.event.<event_name>`, `T7.rollback`, `T9.retire`.
  - External events: `usecase.submitted`, `change.requested` and `lifecycle.review_due`, each with a description.
  - The list of `T8.event` names: `safety_breach`, `incident`, `drift`, `cost_overrun`, `kpi_shortfall`, `upstream_change`, `waiver_expiring`.
- [X] T020 [P] [US2] Write `adlc-specs/shared/mcp_servers.yaml` with every server and scope used in TDS §4–§13, each with `owner_role` and a description: `sharepoint`, `confluence`, `portfolio`, `jira`, `arch_repo`, `mcp_registry`, `git`, `ci`, `prompt_registry`, `artifact_store`, `harness`, `eval_store`, `dataset_registry`, `redteam_harness`, `iam`, `dlp_scanner`, `control_library`, `grc`, `servicenow`, `cmdb`, `monitoring`, `cd`, `traffic_manager`, `agent_registry`, `observability`, `feedback`, `kill_switch`
- [X] T021 [P] [US2] Write `adlc-specs/shared/permissions.yaml`:
  - Verbs per Annex A.4 plus those the TDS uses (`open`, `create`, `configure`, `trigger`, `invoke`, `reduce`, `contact`, `promote`, `disable`, `update`).
  - Duty groups (research R-07):
    - `build`: `write:repo.*`, `open:pull_request`, `run:ci_pipeline`, `provision:dev_env`
    - `evaluate`: `write:eval_store`, `invoke:test_env_agent`, `run:online_eval`
    - `deploy`: `run:cd_pipeline.*`, `set:traffic_split`, `trigger:rollback`
- [X] T022 [P] [US2] Write `adlc-specs/shared/evidence_sources.yaml` (`intake`, `env`, `change`, `template`, `dataset`, `trigger`, `release`, `telemetry`, with the fields the TDS uses, and `profile` with the use-case profile fields of SA §5.1: `applicable_artifacts`, `metric_thresholds`, `kpis`, `autonomy_levels`, `autonomy_level_max`, `token_budget`, `parameters`) and `route_destinations.yaml` (`human_completion`, `owning_terminal`, `owning_terminal_owner`, `lifecycle_closed`, `continue`, `itsm`, `rai_board`, `release_board`, `incident_bridge`, `adlc_coe`, with kinds per contracts/spec-files.md)
- [X] T023 [P] [US2] Write `adlc-specs/shared/metrics.yaml` with every metric the converted specs reference, named per Annex A.4 (for example `task_success_rate`, `injection_success_rate`, `jailbreak_success_rate`, `judge_agreement_rate`, `unit_coverage_pct`, `cost_per_task_usd`, `p95_latency_ms`, `safe_fail_rate`, `pii_leak_count`, `policy_violation_rate`, `availability_pct`, `online_eval_score`), each with class, unit, direction and method
- [X] T024 [P] [US2] Write `adlc-specs/shared/guardrails.yaml` per research R-08. Mark every entry `proposed_default: true` and give it a `source` (TDS section).
  - `injection_success_max` {0.05, 0.02, 0.01}
  - `jailbreak_success_max` {0.05, 0.02, 0.01}
  - `judge_agreement_min` {0.85 ×3}
  - `unit_coverage_min_pct` {80 ×3}
  - `test_scenarios_min_count` {15, 30, 50}
  - `eval_cases_min_count` {100, 250, 500}
  - `human_label_cases_min_count` {50, 100, 200}
  - `rai_metric_classes_required` with direction `superset`: {[toxicity, hallucination], [toxicity, hallucination, pii_leak], [toxicity, bias, hallucination, pii_leak]}
- [X] T025 [US2] Write `adlc-specs/shared/predicates.yaml`. Each predicate has typed params and a description. Fill it while converting (US3), starting with `evidence_exists`, `is_signed`, `is_frozen`, `is_provisioned`, `is_pinned`, `in_directory`, `all_rows_have`, `all_rows_numeric`, `all_metrics_meet_thresholds`, `every_req_traced`, `hash_matches`, `within_window`, `no_expired_waivers`, `any_design_deviation`
- [X] T026 [US2] Implement typed catalogue views in `src/adlc/spec_toolkit/catalogues.py` so T015 passes
- [X] T027 [US2] Implement S-02 in `src/adlc/spec_toolkit/schema.py` (catalogue schema validation, mapping jsonschema `absolute_path` to `bundle.location`), V-18 (catalogue-side naming) and V-19 (tighten-only monotonicity, including `superset` direction) in `src/adlc/spec_toolkit/rules/cross_spec.py`. Make the US2 fixtures pass.

**Checkpoint**: catalogues validate cleanly; their negative fixtures are caught.

---

## Phase 4: User Story 1 - Validate the folder in one command (Priority: P1)

**Goal**: `adlc-spec validate` runs L1–L5 with every rule in contracts/validation-rules.md.

**Independent Test**: the `_valid` bundle gives 0 findings; every rule's fixture gives its finding; the CLI exit codes and both output formats match contracts/adlc-spec-cli.md.

### Tests for US1 (write first) ⚠️

- [X] T028 [P] [US1] Add negative fixtures for the L2 and L3 rules: S-01 (unknown field `rul`; wrong type; missing `timeline.clarification_sla`), S-03 (playbook missing `version`; checklist item without `text`), V-01 (duplicate `CTL-` id in one spec), V-04, V-05 (sign-off role holds only C), V-07, V-08, V-09, V-11 (bad CEL), V-14 (conditional without `when`), V-15 (reviewer holds `pass`; orchestrator holds `terminate`), V-20 and V-21, under `tests/fixtures/specs/<id>-*/`
- [X] T029 [P] [US1] Add negative fixtures for the L4 rules: V-01 (two files, same id), V-02 (reference to an unknown column; reference to a terminal that cannot reach the referrer), V-03, V-05 (unknown role), V-06, V-10 (missing playbook version; checklist item id not in file), V-12 (unknown `param.`; unknown predicate; unknown evidence source; unknown root cause), V-13 (wrong arity), V-16 (allow spans build+deploy), V-17, V-18 (spec-side `CTL` id pattern; agent id not kebab-case), V-22, V-23 (unused predicate gives `info`) and V-26 (proposed default gives `warning`)
- [X] T030 [P] [US1] Write `tests/unit/spec_toolkit/test_versioning.py` using a temporary git repo:
  - V-24: content change without bump, at each bump level in the R-10 table.
  - V-25: version decrease.
  - A new file passes.
  - A missing baseline ref gives a V-24 `warning`.
  - `--no-baseline` skips.
- [X] T031 [P] [US1] Write `tests/unit/spec_toolkit/test_expressions.py`:
  - `parse(expr)` returns the identifier roots and call names for each expression shape in research R-01.
  - A malformed expression gives a parse error with its column.
  - The CEL macros `all`, `exists` and `exists_one` used as methods are not reported as unknown functions.
- [X] T032 [P] [US1] Write `tests/unit/spec_toolkit/test_cli_validate.py` (Typer `CliRunner`): exit 0, 1 and 2; `--format json` matches the contract shape; `--min-severity error` hides warnings without changing the exit code

### Implementation for US1

- [X] T033 [US1] Write `adlc-specs/schema/terminal.schema.json` and `adlc-specs/schema/checklist.schema.json` (draft 2020-12).
  - Cover the full TDS Annex B dictionary, with `$defs` for B.1 types, plus every addition in research R-16.
  - Use `additionalProperties: false` everywhere.
  - Patterns per Annex A.2 for `PRE-`, `CTL-`, `CHK-`, `PB-` and `MON-` ids and agent ids.
  - Also write `adlc-specs/schema/playbook-front-matter.schema.json`.
- [X] T034 [US1] Implement S-01 and S-03 in `src/adlc/spec_toolkit/schema.py`; complete `tests/fixtures/specs/_valid/` so it passes S-01 to S-03
- [X] T035 [US1] Implement `parse_expression(text) -> ParsedExpression(roots, calls, members)` in `src/adlc/spec_toolkit/expressions.py` with `celpy.celparser.CELParser` (parse only), so T031 passes
- [X] T036 [US1] Implement the L3 rules V-01 (within spec), V-04, V-05 (sign-off A/R), V-07, V-08, V-09, V-11, V-14, V-15, V-18 (spec-side patterns not covered by schema), V-20 and V-21 in `src/adlc/spec_toolkit/rules/single_spec.py`. Iterate generically over spec content; no terminal ids in code.
- [X] T037 [US1] Implement the event and route graph in `src/adlc/spec_toolkit/graph.py` per research R-06: terminal and event nodes, special destination sinks, and the emitted events derived from each spec. Add tests in `tests/unit/spec_toolkit/test_graph.py` for the `_valid` bundle.
- [X] T038 [US1] Implement the L4 rules V-01 (across files), V-02 (column and emitted-value resolution plus `nx.has_path`), V-03, V-05 (roles exist), V-06, V-10, V-12, V-13, V-16, V-17, V-22, V-23 and V-26 in `src/adlc/spec_toolkit/rules/cross_spec.py`
- [X] T039 [US1] Implement the L5 rules V-24 and V-25 in `src/adlc/spec_toolkit/rules/versioning.py`: git baseline through `git show <ref>:<path>` (subprocess, no shell) and change classification per the research R-10 table, comparing normalised JSON by section. Expose `compare(baseline_json, current_json) -> BumpLevel` for reuse by registration.
- [X] T040 [US1] Implement `adlc-spec validate` in `src/adlc/spec_toolkit/cli.py` per contracts/adlc-spec-cli.md (options, exit codes, `ADLC_SPEC_BASELINE_REF`) so T032 passes. Run `make lint typecheck` and every US1 test.

**Checkpoint**: every rule fixture is caught (SC-002); `_valid` is clean.

---

## Phase 5: User Story 3 - Converted T0–T9 specs (Priority: P1)

**Goal**: `adlc-specs/terminals/T0.yaml` … `T9.yaml` pass L1–L5 with zero errors, are faithful to TDS §4–§13, and have every change recorded.

**Independent Test**: `uv run adlc-spec validate adlc-specs` gives 0 errors; `CONVERSION.md` accounts for every TDS element (SC-003); no free-text rules remain (SC-004).

### Tests for US3 (write first) ⚠️

- [X] T041 [P] [US3] Write `tests/unit/spec_toolkit/test_repository_specs.py`: validating `adlc-specs/` (no baseline) gives zero `error` findings; ten terminal files `T0`–`T9` exist; every control `rule` and prerequisite `condition` parses as CEL (SC-004); every spec has `status: active` and `schema_version: "1.1.0"`
- [X] T042 [P] [US3] Write `tests/unit/spec_toolkit/test_conversion_record.py`. For each terminal it parses `adlc-specs/CONVERSION.md` and asserts that every `PRE-`, `CTL-`, `CHK-` and `MON-` id, every artifact id, every trigger event and every outcome status from the TDS section appears in the record. Read the TDS ids from `docs/terminal-design-spec.md` with a regex over that terminal's YAML block (SC-003).

### Implementation for US3

Each terminal task below:

- converts the TDS block into the new file;
- writes the `checklists/t<n>.yaml` items with text and creates the playbook stubs it references;
- adds the predicates and metrics it needs to the catalogues;
- appends its section to `adlc-specs/CONVERSION.md`;
- leaves `uv run adlc-spec validate adlc-specs` with no errors for that file.

Free-text rules become CEL or predicate calls, with the TDS text in `description`
(research R-01, R-02). Numeric safety limits become `param.*` references (research R-08).
Every artifact gets `applicability`. Every timeline gets `clarification_sla` (= its
`reminder_after`), `max_clarification_rounds: 2` and `max_auto_retries: 3`. Annex A renames
are applied.

- [X] T043 [US3] Convert T0 (TDS §4) to `adlc-specs/terminals/T0.yaml`, with `checklists/t0.yaml` and stubs `playbooks/t0-intake.md`, `agentic-suitability-rubric.md` and `risk-classification.md`. Example conversions: `"length >= 200 chars"` → `size(intake.free_text) >= 200`; `"exists in directory"` → `in_directory(intake.business_owner)`; `exception` with no route → `route: T1` (TDS §3 default "next terminal").
- [X] T044 [US3] Convert T1 (TDS §5) to `adlc-specs/terminals/T1.yaml`. Its tiering moves to the guardrails `test_scenarios_min_count` and `rai_metric_classes_required`. CTL-T1-05 references `param`/`profile` autonomy limits. Rework routes: `requirement` → T1, `qualification` → T0.
- [X] T045 [US3] Convert T2 (TDS §6) to `adlc-specs/terminals/T2.yaml`. Keep threat-model depth and architecture board review in `controls.tiering`.
- [X] T046 [US3] Convert T3 (TDS §7) to `adlc-specs/terminals/T3.yaml`:
  - CTL-T3-02 → `unit_coverage_pct >= param.unit_coverage_min_pct`
  - `sign_off.plus` → `[{role: solution_architect, when: "any_design_deviation(T3.design_conformance)"}]`
  - `candidate_package` keeps the `sha256` column that T4–T7 bind to
- [X] T047 [US3] Convert T4 (TDS §8) to `adlc-specs/terminals/T4.yaml`:
  - CTL-T4-05 → `judge_agreement_rate >= param.judge_agreement_min`
  - Its tiering case counts move to guardrails; `adversarial` stays in tiering
  - `escalate.when` covers "judge dispute" through a predicate
  - Root-cause routes: implementation → T3, design → T2, requirement → T1
- [X] T048 [US3] Convert T5 (TDS §9) to `adlc-specs/terminals/T5.yaml`:
  - `tier.max_injection_success` → `param.injection_success_max`, and the same for jailbreak
  - Keep tiered sign-off with `board: rai_board`
  - Exception `set_by: [risk_owner]`, `route: T6`, `recheck_at: [T6, T8]`
  - Escalate route `rai_board`
- [X] T049 [US3] Convert T6 (TDS §10) to `adlc-specs/terminals/T6.yaml`:
  - `"T0..T5.status all in [...]"` → a predicate call over a terminal list
  - Rework `missing_evidence` → special destination `owning_terminal`
  - The exception example moves to `description`
  - Escalate → `release_board` with notify `[business_owner]`
- [X] T050 [US3] Convert T7 (TDS §11) to `adlc-specs/terminals/T7.yaml`:
  - Keep `trigger.window`, `controls.auto_rollback_on` and `exception: {not_allowed: true}`
  - `expected_duration` becomes `{low: 1d, medium: 2d, high: 5d}`, with hypercare durations in tiering, as recorded in the conversion record
  - `escalate_after: window_end`
  - `max_rework_cycles: 2`
  - Orchestrator status right `rework_on_auto_rollback`
- [X] T051 [US3] Convert T8 (TDS §12) to `adlc-specs/terminals/T8.yaml`:
  - `mode: continuous` with `review_schedule`
  - `monitors[].raises` and `event_routes` keys become `T8.event.<name>`
  - Free-text monitor thresholds become expressions or predicates
  - `timeline.reminder_after: 2d` and `escalate_after: 7d`, measured from `review_due` (research R-16)
  - Status right `agent: [raise_event]`
- [X] T052 [US3] Convert T9 (TDS §13) to `adlc-specs/terminals/T9.yaml`:
  - `change_classes` with `reentry` and `path`
  - `retirement_procedure`
  - Artifacts `retirement_record` and `closure_report` become conditional (`run.mode == "retire"`)
  - `pass.route: "${T9.change_impact_assessment.reentry_terminal}"` with `alternatives: [lifecycle_closed]`
  - Sign-off per mode `evolve`/`retire`
  - `expected_duration` per research R-16, recorded in the conversion record
- [X] T053 [US3] Write `adlc-specs/schema/DICTIONARY-CHANGES.md` (every row of research R-16, final form) and finish `adlc-specs/CONVERSION.md` with an intro, per-terminal tables (TDS element, TDS location, result `kept|converted|renamed|moved|removed`, new location, reason) and a "proposed defaults" list (FR-017). Run T041 and T042 and make them pass.

**Checkpoint**: the real `adlc-specs/` is clean, the conversion is recorded, and the playbooks and checklists exist (V-10).

---

## Phase 6: User Story 4 - Register specs into the registry (Priority: P1)

**Goal**: migration `0002` plus `adlc-spec register`: transactional, idempotent, version-checked, immutable.

**Independent Test**: on an empty database, registration creates every row; a rerun writes nothing; a changed spec without a bump is refused; a bump deprecates the old version; updates and deletes are refused.

### Tests for US4 (write first) ⚠️

- [X] T054 [P] [US4] Write `tests/integration/spec_toolkit/test_spec_schema_immutability.py` (core rule, constitution IX), using the `migrated_db` fixture from 001:
  - For every table in data-model.md, UPDATE, DELETE and TRUNCATE as `adlc_owner` and `adlc_app` are refused with SQLSTATE `42501`.
  - The exception is `spec_registry`/`spec_catalogue` status: `active→deprecated`, `active→retired` and `deprecated→retired` succeed as owner, but `deprecated→active`, `retired→*`, and changing `content_hash` together with status are refused.
  - A second `active` row for the same `terminal_id` is refused (partial unique index).
  - Retiring a version referenced by `usecase_spec_pin` is refused.
  - `adlc_app` has SELECT only on schema `spec`.
- [X] T055 [P] [US4] Write `tests/unit/spec_toolkit/test_projections.py` (pure, from the `_valid` bundle plus one T8-like and one T9-like fixture):
  - Exact projection rows for triggers, outcome routes (root-cause rows, `requires`, `recheck_at`, `set_by`, `notify`, `alternatives`, `destination_kind`), event routes (`immediate`, `then_destination`), change classes and timelines.
  - One timeline row per tier, with untiered values repeated; `continuous` has a null `expected_duration`.
- [X] T056 [P] [US4] Write `tests/integration/spec_toolkit/test_register.py`:
  - First run registers 10 terminals, every catalogue and every playbook.
  - Second run reports `0 registered`.
  - A changed T0 content under the same version is refused (R-01) with nothing written.
  - A T0 bump to `1.0.1` (description-only change) registers and deprecates `1.0.0`; the old row is otherwise unchanged.
  - A playbook with the same version but a changed hash is refused.
  - A bundle with validation errors is refused before connecting.
  - `--dry-run` leaves no rows.
  - An exception injected after the first projection insert (monkeypatched) leaves no rows at all (interrupted registration edge case).
  - Two concurrent registrations (threads) end with exactly one active row per terminal, and the second reports no changes.
  - Registering the real `adlc-specs/` into the throwaway database completes in under 30 s (SC-005, FR-023b).

### Implementation for US4

- [X] T057 [US4] Write migration `db/migrations/versions/0002_spec_registry.py` per data-model.md.
  - Tables `spec.spec_registry`, `spec.spec_catalogue`, `spec.playbook_registry`, `spec.spec_trigger`, `spec.spec_outcome_route`, `spec.spec_event_route`, `spec.spec_change_class`, `spec.spec_timeline` and `spec.usecase_spec_pin`, with the constraints quoted in the data model:
    - `content_hash` `CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$')`
    - `status IN ('active','deprecated','retired')`
    - `terminal_id ~ '^T[0-9]+$'`
    - `playbook_id ~ '^PB-(T[0-9]+|SH)-[0-9]{2}$'`
    - `usecase_id ~ '^UC-[0-9]{4}$'`
    - `UNIQUE (terminal_id, version)`
    - partial unique index `WHERE status = 'active'`
    - the unique keys of each projection table
  - Functions `spec.reject_mutation()` and `spec.guard_status_transition()` (research R-11).
  - `BEFORE UPDATE OR DELETE` row triggers and `BEFORE TRUNCATE` statement triggers on every table.
  - `GRANT USAGE` and `SELECT` on all `spec` tables to the app role.
  - The downgrade drops everything in reverse.
  - Extend `scripts/migration_check.py` to assert the new tables and triggers.
- [X] T058 [US4] Implement `projections.py` (pure: spec JSON → typed rows) so T055 passes
- [X] T059 [US4] Implement `register.py` per research R-12:
  - Validate first.
  - In one owner transaction, take `pg_advisory_xact_lock(hashtext('adlc.spec.register'))`.
  - Process catalogues, then terminals, then playbooks: compare hashes; for a new version use `versioning.compare` against the registered JSON; deprecate the old active row, insert the new row and its projections.
  - Return a `RegistrationReport`; `--dry-run` rolls back.
  - Log one summary line.
- [X] T060 [US4] Implement `adlc-spec register [--dry-run]` in `cli.py` using `load_settings_or_exit(DatabaseSettings)` and `owner_engine` from 001. Output and exit codes per contracts/adlc-spec-cli.md. Make T054 and T056 pass.

**Checkpoint**: the registry is populated, idempotent and immutable.

---

## Phase 7: User Story 5 - Route lookups (Priority: P2)

**Goal**: the `SpecRegistry` Protocol with SQL and in-memory implementations that give identical answers.

**Independent Test**: the demo routing table in contracts/spec-registry-interface.md passes against both implementations.

### Tests for US5 (write first) ⚠️

- [X] T061 [P] [US5] Write `tests/integration/spec_toolkit/test_demo_routing.py` (SC-007, test-first). After registering the real `adlc-specs/` into the test database, every row of the demo routing table returns the expected answer from `SqlSpecRegistry` and from `InMemorySpecRegistry.from_bundle(...)`, and the two are equal. Unknown event, root cause and terminal return `()` or `None`.
- [X] T062 [P] [US5] Write `tests/integration/spec_toolkit/test_registry_versions.py`: with T0 at `1.0.0` (deprecated) and `1.0.1` (active), reads without `version` use `1.0.1`, and reads with `version="1.0.0"` use the old projections

### Implementation for US5

- [X] T063 [US5] Implement in `src/adlc/spec_toolkit/registry.py`: the `SpecRegistry` Protocol and the frozen result dataclasses (`TerminalRef`, `RouteTarget`, `EventRouteTarget`, `ChangeClassRoute`, `TimelinePolicy`, `RegistryEntry`, `CatalogueEntry`) per contracts/spec-registry-interface.md; `SqlSpecRegistry(engine)` (SQLAlchemy Core, app identity); and `InMemorySpecRegistry.from_bundle(bundle)`, which reuses `projections.py`. Make T061 and T062 pass.

- [X] T072 [US5] Write failing tests, then implement the role catalogue cross-check (FR-025 exception).
  - Tests go in `tests/integration/spec_toolkit/test_role_catalogue_consistency.py`.
  - At API start, `create_app` compares the content hash of the role file it loaded with the active `roles` catalogue in the registry, through `SpecRegistry.catalogue("roles")`.
  - On a mismatch, startup stops with `adlc: configuration error` naming both versions.
  - When no `roles` catalogue is registered yet, it logs a WARNING and continues.
  - Implement in `src/adlc/api/app.py` using `normalise.content_hash`.

**Checkpoint**: 003 can depend on `SpecRegistry`.

---

## Phase 8: User Story 6 - Editor support and CI gate (Priority: P2)

**Goal**: editors validate the YAML; `make check` blocks invalid specs; Compose registers on `make up`.

**Independent Test**: break a spec, and `make check` fails at `==> spec-validate`. `make up` runs `migrate → register → api`, and the API is healthy.

- [X] T064 [P] [US6] Add `# yaml-language-server: $schema=../schema/terminal.schema.json` as the first line of every `adlc-specs/terminals/*.yaml`, the matching catalogue schema line to every `adlc-specs/shared/*.yaml`, and the checklist schema line to `adlc-specs/checklists/*.yaml`. Add a test in `tests/unit/spec_toolkit/test_repository_specs.py` that every YAML file declares its schema (FR-026).
- [X] T065 [US6] Add `spec-validate` (`$(UV) adlc-spec validate adlc-specs --baseline-ref $${ADLC_SPEC_BASELINE_REF:-origin/main}`) and `spec-register` to `Makefile`. Insert `spec-validate` into `check` between `typecheck` and `test`. Update `tests/unit/test_build_contract.py` (target list and `check` order) and `specs/001-platform-foundation/contracts/make-targets.md`.
- [X] T066 [US6] In `deploy/compose.yaml`, add the one-shot `register` service (API image, `command: ["adlc-spec", "register", "adlc-specs"]`, owner settings like `migrate`, `depends_on: migrate: service_completed_successfully`). Make `api` depend on `register` completing. Bring the stack up and confirm `make status` shows `register` exited 0.
- [X] T067 [US6] Set `fetch-depth: 0` on `actions/checkout` in `.github/workflows/ci.yml`, so L5 can read `origin/main` (`tests/unit/test_build_contract.py` still sees only `make` runs)

---

## Phase 9: Polish & Cross-Cutting

- [X] T068 [P] Extend `tests/unit/test_no_hardcoded_values.py` so its terminal-id, event and role scan covers `src/adlc/spec_toolkit/**` (constitution I), and confirm it passes. Add `*/adlc/spec_toolkit/*` to `CORE_MODULES` in `Makefile` so the 80% core coverage gate includes routing and registry code (constitution IX).
- [X] T069 [P] Write `src/adlc/spec_toolkit/README.md` (commands, rule levels, how to add a rule with its fixture, read interface) and update the root `README.md` command table (`spec-validate`, `spec-register`)
- [X] T070 Run quickstart.md steps 1–6 on the live stack and record a "Validation run" section in `specs/002-terminal-spec-toolkit/quickstart.md`, including the `make spec-validate` timing (SC-001) and the registration timing (SC-005)
- [X] T071 Run `make check` on a clean clone of the branch; fix anything that fails

---

## Dependencies & Execution Order

- **Setup → Foundational → US2 → US1 → US3 → US4 → US5 → US6 → Polish.**
- US1's L4 rules need the US2 catalogue views. US3 needs the US1 validator to prove each
  conversion. US4 registers the US3 specs (its unit tests use fixtures, so T054, T055 and T058
  can start after Foundational). US5 reads what US4 writes. US6 wires everything into
  make, Compose and CI.
- **Within each story**: fixtures and tests → implementation → story checkpoint.

### Parallel opportunities

- Foundational: T005/T006, T007, T009/T010 and T013 in parallel.
- US2: catalogue files T018–T024 in parallel (different files); T016 alongside them.
- US1: fixture tasks T028/T029 and tests T030–T032 in parallel.
- US3: conversions are sequential (shared catalogues, predicates and CONVERSION.md), but T041 and T042 can be written in parallel up front.
- US4: T054, T055, T056 in parallel; T057 (migration) alongside T058 (pure projections).
- US6: T064 and T067 in parallel.

## Parallel Example: User Story 2

```text
Together: T018 risk tiers etc. · T019 events · T020 MCP servers · T021 permissions · T022 sources/destinations · T023 metrics · T024 guardrails · T016 schemas
Then:     T025 predicates (grows during US3) → T026 views → T027 S-02 / V-18 / V-19
```

## Implementation Strategy

1. Setup → Foundational → US2 → US1: a working validator over the catalogues and fixtures.
2. US3: real T0–T9 specs, validated one by one. **Stop and review the conversion record with
   the CoE** (largest judgement area).
3. US4 → US5: registry and lookups; feature 003 can start against `SpecRegistry`.
4. US6 → Polish: gates, Compose, docs; then `/speckit-converge`.
