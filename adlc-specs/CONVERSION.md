# Conversion record: TDS §4–§13 → adlc-specs/terminals

Feature 002 converted the ten terminal specs of the Terminal Design Specification (TDS) into
validated YAML (dictionary 1.1.0, see `schema/DICTIONARY-CHANGES.md`). This record lists every
TDS element and what happened to it, so the TDS can be updated and every judgement call reviewed.

## Rules applied to every terminal

- Free-text conditions and rules became CEL expressions or calls to predicates in `shared/predicates.yaml`; the TDS wording is kept as `description` (spec FR-013).
- Run variables are namespaced (`run.rework_count`, `run.age`, `run.mode`), the spec's own timeline as `timeline.*`, guardrails as `param.*`. Escalation `rework_count > 3` reads `timeline.max_rework_cycles` instead of a literal.
- `required: true` became `applicability: {mode: mandatory}`; `required: on_retire` became conditional on `run.mode == "retire"` (SA §5.2).
- Every timeline gained `clarification_sla` (= `reminder_after`), `max_clarification_rounds: 2` and `max_auto_retries: 3` (SA §6.2, TDS Annex A.3 note).
- Checklist item text moved to `checklists/t<n>.yaml`; specs list item ids only. Playbooks referenced by the TDS exist as versioned stubs in `playbooks/`.
- An `exception` outcome without a route takes the pass route (TDS §3: "Next terminal").
- Numeric artifact columns carry SA Annex A unit suffixes (`_count`, `_pct`, `_usd`, `_rate`); renames are listed per artifact below. This is a conversion convention, not a validation rule, because the dictionary does not type columns.
- Mechanical outcome changes in every terminal (rows marked "converted" with no specific note): `set_by` is always a list of roles, `escalate.when` is CEL reading `timeline.*`, and free-text `when` wording is kept as `description`.
- Numeric safety and assurance limits moved to `shared/guardrails.yaml` (spec FR-014); process-depth settings stay in `controls.tiering`.

## Proposed defaults awaiting owner confirmation (TDS §15, spec FR-017)

- All nine guardrails in `shared/guardrails.yaml` (`proposed_default: true`; validation reports them as V-26 warnings).
- Literal limits kept in specs: CTL-T0-03 suitability mean ≥ 3.0, CTL-T0-04 similarity < 0.85, MON-05 7d, MON-06 3 reviews, MON-09 14d.
- All timeline durations and `max_rework_cycles` (TDS values), plus the new `clarification_sla`, `max_clarification_rounds: 2` and `max_auto_retries: 3`.
- T7 tiering `canary_pct`, `soak`, `hypercare`; T8 `review_schedule`.

## T0 – Intake & Qualification

Source: TDS §4. File: `terminals/T0.yaml`.

| TDS element | TDS location | Result | New location | Reason |
| --- | --- | --- | --- | --- |
| `usecase.submitted` | trigger.on | kept | trigger.on |  |
| `T9.reentry.T0` | trigger.on | kept | trigger.on |  |
| `T1.rework.qualification` | — | added | trigger.on | Added so the rework root-cause route that targets this terminal has a subscription (V-17). |
| `PRE-T0-01` | prerequisites | converted | prerequisites | `length >= 200 chars` → `size(intake.free_text) >= 200` |
| `PRE-T0-02` | prerequisites | converted | prerequisites | `exists in directory` → `in_directory(intake.business_owner)` |
| `CTL-T0-01` | controls.automated | converted | controls.automated | `all required artifacts present` → `all_required_artifacts_present()` |
| `CTL-T0-02` | controls.automated | converted | controls.automated | `risk_tier in [low, medium, high]` → `all_rows_in(T0.risk_classification, "tier", ["low", "medium", "high"])` |
| `CTL-T0-03` | controls.automated | converted | controls.automated | `suitability_score >= 3 of 5` → `column_mean(T0.agentic_suitability, "score_1_5") >= 3.0` |
| `CTL-T0-04` | controls.automated | converted | controls.automated | `no duplicate agent in portfolio (similarity < 0.85)` → `portfolio.max_similarity < 0.85` |
| `CHK-T0-01` | controls.checklist.items | moved | checklists/t0.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T0-02` | controls.checklist.items | moved | checklists/t0.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T0-03` | controls.checklist.items | moved | checklists/t0.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T0-04` | controls.checklist.items | moved | checklists/t0.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T0-05` | controls.checklist.items | moved | checklists/t0.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T0-06` | controls.checklist.items | moved | checklists/t0.yaml | Text moved to the checklist file; spec keeps the id |
| `intake_card` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `business_problem` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `agentic_suitability` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `value_hypothesis` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `risk_classification` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `data_access` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `initial_rai_security` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `feasibility` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `raci` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `pass` | outcome_model | kept | outcome_model |  |
| `rework` | outcome_model | kept | outcome_model |  |
| `exception` | outcome_model | converted | outcome_model | see notes below |
| `escalate` | outcome_model | converted | outcome_model | see notes below |
| `terminate` | outcome_model | converted | outcome_model | see notes below |
| `timeline.expected_duration` | timeline | kept | timeline |  |
| `timeline.reminder_after` | timeline | kept | timeline |  |
| `timeline.escalate_after` | timeline | kept | timeline |  |
| `timeline.max_rework_cycles` | timeline | kept | timeline |  |

Notes:

- `exception` had no route; set to `T1`, the pass route (TDS §3 default: next terminal).
- CTL-T0-03 and CTL-T0-04 keep their literal limits (3.0, 0.85); they are advisory quality checks, not safety guardrails. Proposed defaults.

## T1 – Requirements & Outcome

Source: TDS §5. File: `terminals/T1.yaml`.

| TDS element | TDS location | Result | New location | Reason |
| --- | --- | --- | --- | --- |
| `T0.pass` | trigger.on | kept | trigger.on |  |
| `T0.exception` | trigger.on | kept | trigger.on |  |
| `T9.reentry.T1` | trigger.on | kept | trigger.on |  |
| `T4.rework.requirement` | trigger.on | kept | trigger.on |  |
| `T2.rework.requirement` | — | added | trigger.on | Added so the rework root-cause route that targets this terminal has a subscription (V-17). |
| `PRE-T1-01` | prerequisites | converted | prerequisites | `in [pass, exception]` → `T0.status in ["pass", "exception"]` |
| `PRE-T1-02` | prerequisites | converted | prerequisites | `exists` → `evidence_exists(T0.risk_classification.tier)` |
| `PRE-T1-03` | prerequisites | converted | prerequisites | `exists` → `evidence_exists(T0.value_hypothesis)` |
| `CTL-T1-01` | controls.automated | converted | controls.automated | `every requirement has id, priority, acceptance_criteria` → `all_rows_have(T1.functional_requirements, ["req_id", "priority", "acceptance_criteria"])` |
| `CTL-T1-02` | controls.automated | converted | controls.automated | `every KPI has numeric baseline and target` → `all_rows_numeric(T1.kpis, ["baseline", "target"])` |
| `CTL-T1-03` | controls.automated | converted | controls.automated | `every eval and RAI threshold is numeric with operator` → `all_rows_numeric(T1.eval_thresholds, ["threshold"]) && all_rows_have(T1.eval_thresholds, ["operator"]) && all_rows_numeric(T1.rai_thresholds, ["threshold"]) && all_rows_have(T1.rai_thresholds, ["operator"])` |
| `CTL-T1-04` | controls.automated | converted | controls.automated | `autonomy_level defined for every agent action` → `all_rows_have(T1.autonomy_levels, ["autonomy_level"])` |
| `CTL-T1-05` | controls.automated | converted | controls.automated | `autonomy_level <= max allowed for risk_tier` → `column_max(T1.autonomy_levels, "autonomy_level") <= param.autonomy_level_max` |
| `CTL-T1-06` | — | added | controls.automated | test scenarios meet the tier minimum (TDS tiering min_test_scenarios, now a guardrail) |
| `CHK-T1-01` | controls.checklist.items | moved | checklists/t1.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T1-02` | controls.checklist.items | moved | checklists/t1.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T1-03` | controls.checklist.items | moved | checklists/t1.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T1-04` | controls.checklist.items | moved | checklists/t1.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T1-05` | controls.checklist.items | moved | checklists/t1.yaml | Text moved to the checklist file; spec keeps the id |
| `functional_requirements` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `non_functional_requirements` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `behavioural_requirements` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `autonomy_levels` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `kpis` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `eval_thresholds` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `rai_thresholds` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `user_experience` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `acceptance_and_failure` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `pass` | outcome_model | kept | outcome_model |  |
| `rework` | outcome_model | kept | outcome_model |  |
| `exception` | outcome_model | converted | outcome_model | see notes below |
| `escalate` | outcome_model | converted | outcome_model | see notes below |
| `terminate` | outcome_model | converted | outcome_model | see notes below |
| `min_test_scenarios` | controls.tiering | moved | shared/guardrails.yaml | numeric safety/assurance limit → guardrail (FR-014) |
| `rai_thresholds_required` | controls.tiering | moved | shared/guardrails.yaml | numeric safety/assurance limit → guardrail (FR-014) |
| `timeline.expected_duration` | timeline | kept | timeline |  |
| `timeline.reminder_after` | timeline | kept | timeline |  |
| `timeline.escalate_after` | timeline | kept | timeline |  |
| `timeline.max_rework_cycles` | timeline | kept | timeline |  |

Notes:

- `controls.tiering` (`min_test_scenarios`, `rai_thresholds_required`) moved to guardrails `test_scenarios_min` and `rai_metric_classes_min`; the tiering block is removed.
- New control `CTL-T1-06` enforces `param.test_scenarios_min`, which the TDS stated only as a tier value.
- CTL-T1-05 uses guardrail `autonomy_level_max` (TDS §15 open decision; proposed 2 / 3 / 4, not monotonic because the tier is set by autonomy).
- `exception` had no route; set to `T2`.

## T2 – Architecture & Design

Source: TDS §6. File: `terminals/T2.yaml`.

| TDS element | TDS location | Result | New location | Reason |
| --- | --- | --- | --- | --- |
| `T1.pass` | trigger.on | kept | trigger.on |  |
| `T1.exception` | trigger.on | kept | trigger.on |  |
| `T9.reentry.T2` | trigger.on | kept | trigger.on |  |
| `T3.rework.design` | trigger.on | kept | trigger.on |  |
| `T4.rework.design` | trigger.on | kept | trigger.on |  |
| `T5.rework.architecture` | trigger.on | kept | trigger.on |  |
| `PRE-T2-01` | prerequisites | converted | prerequisites | `in [pass, exception]` → `T1.status in ["pass", "exception"]` |
| `PRE-T2-02` | prerequisites | converted | prerequisites | `exists` → `evidence_exists(T1.non_functional_requirements)` |
| `PRE-T2-03` | prerequisites | converted | prerequisites | `exists` → `evidence_exists(T1.autonomy_levels)` |
| `CTL-T2-01` | controls.automated | converted | controls.automated | `every T1 requirement mapped to >= 1 design decision` → `every_req_mapped(T1.functional_requirements, T2.design_decisions)` |
| `CTL-T2-02` | controls.automated | converted | controls.automated | `all tools in approved MCP registry or flagged as new` → `all_tools_registered_or_flagged(T2.tool_api_contracts)` |
| `CTL-T2-03` | controls.automated | converted | controls.automated | `token_budget per task defined and <= T1 cost NFR` → `token_budget_within_nfr(T2.token_budget, T1.non_functional_requirements)` |
| `CTL-T2-04` | controls.automated | converted | controls.automated | `data classes handled <= T0 data classification approval` → `data_classes_within(T2.data_strategy, T0.data_access)` |
| `CTL-T2-05` | controls.automated | converted | controls.automated | `HITL design covers every action with hitl_required = true` → `hitl_covered(T1.autonomy_levels, T2.hitl_design)` |
| `CHK-T2-01` | controls.checklist.items | moved | checklists/t2.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T2-02` | controls.checklist.items | moved | checklists/t2.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T2-03` | controls.checklist.items | moved | checklists/t2.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T2-04` | controls.checklist.items | moved | checklists/t2.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T2-05` | controls.checklist.items | moved | checklists/t2.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T2-06` | controls.checklist.items | moved | checklists/t2.yaml | Text moved to the checklist file; spec keeps the id |
| `solution_overview` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `system_architecture` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `data_strategy` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `agentic_pattern` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `model_strategy` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `tool_api_contracts` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `memory_context_strategy` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `hitl_design` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `token_budget` | evidence.artifacts | renamed | evidence.artifacts | columns `task, max_tokens, max_cost, on_exceed` → `task, max_tokens, max_cost_usd, on_exceed` (Annex A); applicability mandatory |
| `security_architecture` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `observability_design` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `rai_metric_emission` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `deployment_architecture` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `design_decisions` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `pass` | outcome_model | kept | outcome_model |  |
| `rework` | outcome_model | kept | outcome_model |  |
| `exception` | outcome_model | converted | outcome_model | see notes below |
| `escalate` | outcome_model | converted | outcome_model | see notes below |
| `terminate` | outcome_model | converted | outcome_model | see notes below |
| `architecture_board_review` | controls.tiering | kept | controls.tiering |  |
| `threat_model` | controls.tiering | kept | controls.tiering |  |
| `timeline.expected_duration` | timeline | kept | timeline |  |
| `timeline.reminder_after` | timeline | kept | timeline |  |
| `timeline.escalate_after` | timeline | kept | timeline |  |
| `timeline.max_rework_cycles` | timeline | kept | timeline |  |

Notes:

- `security_officer` changed from C to R: the TDS has the role sign off while holding C, which V-05 forbids. CoE to confirm.
- Artifact `token_budget` column `max_cost` renamed `max_cost_usd` (Annex A unit suffix).
- `exception` had no route; set to `T3`.

## T3 – Build & Integration

Source: TDS §7. File: `terminals/T3.yaml`.

| TDS element | TDS location | Result | New location | Reason |
| --- | --- | --- | --- | --- |
| `T2.pass` | trigger.on | kept | trigger.on |  |
| `T2.exception` | trigger.on | kept | trigger.on |  |
| `T9.reentry.T3` | trigger.on | kept | trigger.on |  |
| `T4.rework.implementation` | trigger.on | kept | trigger.on |  |
| `T5.rework.control_missing` | trigger.on | kept | trigger.on |  |
| `T7.rollback` | trigger.on | kept | trigger.on |  |
| `T7.rework.defect` | — | added | trigger.on | Added so the rework root-cause route that targets this terminal has a subscription (V-17). |
| `PRE-T3-01` | prerequisites | converted | prerequisites | `in [pass, exception]` → `T2.status in ["pass", "exception"]` |
| `PRE-T3-02` | prerequisites | converted | prerequisites | `exists` → `evidence_exists(T2.tool_api_contracts)` |
| `PRE-T3-03` | prerequisites | converted | prerequisites | `provisioned` → `is_provisioned(env.dev)` |
| `PRE-T3-04` | prerequisites | converted | prerequisites | `pinned` → `is_pinned(template.version)` |
| `CTL-T3-01` | controls.automated | converted | controls.automated | `ci.status == green` → `ci.status == "green"` |
| `CTL-T3-02` | controls.automated | converted | controls.automated | `unit_coverage >= 80%` → `column_min(T3.test_results, "coverage_pct") >= param.unit_coverage_min` |
| `CTL-T3-03` | controls.automated | converted | controls.automated | `sast.critical == 0 and sast.high == 0` → `scan_clean(T3.security_build_checks, "sast", ["critical", "high"])` |
| `CTL-T3-04` | controls.automated | converted | controls.automated | `secret_scan.findings == 0` → `scan_clean(T3.security_build_checks, "secret_scan", ["critical", "high", "medium"])` |
| `CTL-T3-05` | controls.automated | converted | controls.automated | `every req_id traced to >= 1 test_id` → `every_req_traced(T1.functional_requirements, T3.traceability_matrix, "test_id")` |
| `CTL-T3-06` | controls.automated | converted | controls.automated | `telemetry.traces and rai_metrics emitting in dev` → `all_rows_true(T3.observability_check, "emitting")` |
| `CTL-T3-07` | controls.automated | converted | controls.automated | `all prompts and tools have registry version` → `all_rows_have(T3.build_manifest, ["version", "hash"])` |
| `CTL-T3-08` | controls.automated | converted | controls.automated | `sbom generated and licences approved` → `sbom.generated && sbom.licences_approved` |
| `CHK-T3-01` | controls.checklist.items | moved | checklists/t3.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T3-02` | controls.checklist.items | moved | checklists/t3.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T3-03` | controls.checklist.items | moved | checklists/t3.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T3-04` | controls.checklist.items | moved | checklists/t3.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T3-05` | controls.checklist.items | moved | checklists/t3.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T3-06` | controls.checklist.items | moved | checklists/t3.yaml | Text moved to the checklist file; spec keeps the id |
| `build_manifest` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `traceability_matrix` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `design_conformance` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `test_results` | evidence.artifacts | renamed | evidence.artifacts | columns `suite, total, passed, failed, coverage` → `suite, total_count, passed_count, failed_count, coverage_pct` (Annex A); applicability mandatory |
| `security_build_checks` | evidence.artifacts | renamed | evidence.artifacts | columns `scan, tool, critical, high, medium, status` → `scan, tool, critical_count, high_count, medium_count, status` (Annex A); applicability mandatory |
| `observability_check` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `config_register` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `change_log` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `candidate_package` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `pass` | outcome_model | kept | outcome_model |  |
| `rework` | outcome_model | kept | outcome_model |  |
| `exception` | outcome_model | converted | outcome_model | see notes below |
| `escalate` | outcome_model | converted | outcome_model | see notes below |
| `terminate` | outcome_model | converted | outcome_model | see notes below |
| `timeline.expected_duration` | timeline | kept | timeline |  |
| `timeline.reminder_after` | timeline | kept | timeline |  |
| `timeline.escalate_after` | timeline | kept | timeline |  |
| `timeline.max_rework_cycles` | timeline | kept | timeline |  |

Notes:

- `sign_off.plus` free text became `[{role: solution_architect, when: any_design_deviation(T3.design_conformance)}]`.
- CTL-T3-02 now reads `param.unit_coverage_min` (guardrail, 80 for every tier).
- Numeric columns renamed (Annex A): `test_results` total/passed/failed/coverage → `total_count`/`passed_count`/`failed_count`/`coverage_pct`; `security_build_checks` critical/high/medium → `*_count`.
- `exception` had no route; set to `T4`.

## T4 – Evaluation

Source: TDS §8. File: `terminals/T4.yaml`.

| TDS element | TDS location | Result | New location | Reason |
| --- | --- | --- | --- | --- |
| `T3.pass` | trigger.on | kept | trigger.on |  |
| `T3.exception` | trigger.on | kept | trigger.on |  |
| `T9.reentry.T4` | trigger.on | removed | — | No T9 change class re-enters at this terminal (V-03: event never produced); re-entry stays possible by adding a change class. CoE to confirm. |
| `PRE-T4-01` | prerequisites | converted | prerequisites | `exists` → `evidence_exists(T3.candidate_package.sha256)` |
| `PRE-T4-02` | prerequisites | converted | prerequisites | `exists` → `evidence_exists(T1.eval_thresholds)` |
| `PRE-T4-03` | prerequisites | converted | prerequisites | `exists` → `evidence_exists(T1.rai_thresholds)` |
| `PRE-T4-04` | prerequisites | converted | prerequisites | `deployed_hash == T3.candidate_package.sha256` → `hash_matches(env.test, T3.candidate_package)` |
| `PRE-T4-05` | prerequisites | converted | prerequisites | `approved by data_owner` → `approved_by(dataset.golden, "data_owner")`; evidence_ref `dataset.golden.approval` → `dataset.golden` |
| `CTL-T4-01` | controls.automated | converted | controls.automated | `each metric in T1.eval_thresholds meets operator and threshold` → `all_metrics_meet_thresholds(T4.quality_vs_threshold, T1.eval_thresholds)` |
| `CTL-T4-02` | controls.automated | converted | controls.automated | `each metric in T1.rai_thresholds meets operator and threshold` → `all_metrics_meet_thresholds(T4.rai_vs_threshold, T1.rai_thresholds)` |
| `CTL-T4-03` | controls.automated | converted | controls.automated | `every req_id has >= 1 executed case` → `every_req_traced(T1.functional_requirements, T4.test_case_results, "case_id")` |
| `CTL-T4-04` | controls.automated | converted | controls.automated | `open_defects.critical == 0` → `no_open_rows(T4.defect_log, "severity", ["critical"])` |
| `CTL-T4-05` | controls.automated | converted | controls.automated | `judge_human_agreement >= 0.85` → `column_min(T4.judge_calibration, "agreement_rate") >= param.judge_agreement_min` |
| `CTL-T4-06` | controls.automated | converted | controls.automated | `cost_per_task <= T2.token_budget.max_cost` → `cost_within_budget(T4.cost_latency, T2.token_budget)` |
| `CTL-T4-07` | controls.automated | converted | controls.automated | `p95_latency <= T1 latency NFR` → `latency_within_nfr(T4.cost_latency, T1.non_functional_requirements)` |
| `CTL-T4-08` | controls.automated | converted | controls.automated | `failure-mode safe_fail_rate == 100%` → `all_rows_true(T4.failure_mode_results, "safe_fail")` |
| `CTL-T4-09` | — | added | controls.automated | executed cases meet the tier minimum (TDS tiering min_cases, now a guardrail) |
| `CTL-T4-10` | — | added | controls.automated | human-labelled calibration slice meets the tier minimum (TDS tiering human_label_slice, now a guardrail) |
| `CHK-T4-01` | controls.checklist.items | moved | checklists/t4.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T4-02` | controls.checklist.items | moved | checklists/t4.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T4-03` | controls.checklist.items | moved | checklists/t4.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T4-04` | controls.checklist.items | moved | checklists/t4.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T4-05` | controls.checklist.items | moved | checklists/t4.yaml | Text moved to the checklist file; spec keeps the id |
| `golden_dataset_register` | evidence.artifacts | renamed | evidence.artifacts | columns `dataset_id, version, size, synthetic_pct, real_pct, approver` → `dataset_id, version, size_count, synthetic_pct, real_pct, approver` (Annex A); applicability mandatory |
| `test_case_results` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `quality_vs_threshold` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `rai_vs_threshold` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `cost_latency` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `failure_mode_results` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `defect_log` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `judge_calibration` | evidence.artifacts | renamed | evidence.artifacts | columns `judge, sample_size, agreement` → `judge, sample_size_count, agreement_rate` (Annex A); applicability mandatory |
| `regression_pack` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `pass` | outcome_model | kept | outcome_model |  |
| `rework` | outcome_model | kept | outcome_model |  |
| `exception` | outcome_model | converted | outcome_model | see notes below |
| `escalate` | outcome_model | converted | outcome_model | see notes below |
| `terminate` | outcome_model | converted | outcome_model | see notes below |
| `adversarial` | controls.tiering | kept | controls.tiering |  |
| `human_label_slice` | controls.tiering | moved | shared/guardrails.yaml | numeric safety/assurance limit → guardrail (FR-014) |
| `min_cases` | controls.tiering | moved | shared/guardrails.yaml | numeric safety/assurance limit → guardrail (FR-014) |
| `timeline.expected_duration` | timeline | kept | timeline |  |
| `timeline.reminder_after` | timeline | kept | timeline |  |
| `timeline.escalate_after` | timeline | kept | timeline |  |
| `timeline.max_rework_cycles` | timeline | kept | timeline |  |

Notes:

- `controls.tiering` `min_cases` and `human_label_slice` moved to guardrails `eval_cases_min` and `human_label_cases_min`, enforced by new controls `CTL-T4-09` and `CTL-T4-10`; `adversarial` stays in tiering.
- CTL-T4-05 now reads `param.judge_agreement_min`; `judge_calibration` columns become `sample_size_count`, `agreement_rate`; `golden_dataset_register.size` → `size_count`.
- `exception.when` free text became `no_critical_threshold_missed(...)`.

## T5 – Trust, Risk & Assurance

Source: TDS §9. File: `terminals/T5.yaml`.

| TDS element | TDS location | Result | New location | Reason |
| --- | --- | --- | --- | --- |
| `T4.pass` | trigger.on | kept | trigger.on |  |
| `T4.exception` | trigger.on | kept | trigger.on |  |
| `T9.reentry.T5` | trigger.on | removed | — | No T9 change class re-enters at this terminal (V-03: event never produced); re-entry stays possible by adding a change class. CoE to confirm. |
| `T8.event.safety_breach` | trigger.on | kept | trigger.on |  |
| `PRE-T5-01` | prerequisites | converted | prerequisites | `in [pass, exception]` → `T4.status in ["pass", "exception"]` |
| `PRE-T5-02` | prerequisites | converted | prerequisites | `exists` → `evidence_exists(T4.rai_vs_threshold)` |
| `PRE-T5-03` | prerequisites | converted | prerequisites | `exists` → `evidence_exists(T2.security_architecture)` |
| `PRE-T5-04` | prerequisites | converted | prerequisites | `exists` → `evidence_exists(T2.data_strategy)` |
| `PRE-T5-05` | prerequisites | converted | prerequisites | `deployed_hash == T3.candidate_package.sha256` → `hash_matches(env.test, T3.candidate_package)` |
| `CTL-T5-01` | controls.automated | converted | controls.automated | `injection_success_rate <= tier.max_injection_success` → `redteam.injection_success_rate <= param.injection_success_max` |
| `CTL-T5-02` | controls.automated | converted | controls.automated | `jailbreak_success_rate <= tier.max_jailbreak_success` → `redteam.jailbreak_success_rate <= param.jailbreak_success_max` |
| `CTL-T5-03` | controls.automated | converted | controls.automated | `pii_leak_findings == 0` → `dlp.pii_leak_count == 0` |
| `CTL-T5-04` | controls.automated | converted | controls.automated | `agent identity permissions subset of T2 design` → `permissions_subset(T5.access_control_matrix, T2.security_architecture)` |
| `CTL-T5-05` | controls.automated | converted | controls.automated | `kill_switch_test == pass` → `scenario_passed(T5.resilience_verification, "kill_switch")` |
| `CTL-T5-06` | controls.automated | converted | controls.automated | `findings.critical.unmitigated == 0` → `no_unmitigated_critical(T5.threat_model_results)` |
| `CTL-T5-07` | controls.automated | converted | controls.automated | `every residual risk has risk_owner and decision` → `all_rows_have(T5.residual_risk_register, ["risk_owner", "decision"])` |
| `CHK-T5-01` | controls.checklist.items | moved | checklists/t5.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T5-02` | controls.checklist.items | moved | checklists/t5.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T5-03` | controls.checklist.items | moved | checklists/t5.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T5-04` | controls.checklist.items | moved | checklists/t5.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T5-05` | controls.checklist.items | moved | checklists/t5.yaml | Text moved to the checklist file; spec keeps the id |
| `threat_model_results` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `security_control_evidence` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `access_control_matrix` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `privacy_assessment` | evidence.artifacts | renamed | evidence.artifacts | columns `data_element, class, masking, retention, lawful_basis` → `data_element, data_class, masking, retention, lawful_basis` (Annex A); applicability mandatory |
| `regulatory_map` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `rai_assurance` | evidence.artifacts | renamed | evidence.artifacts | columns `rai_metric, T4_actual, threshold, accepted` → `rai_metric, t4_actual, threshold, accepted` (Annex A); applicability mandatory |
| `resilience_verification` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `residual_risk_register` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `assurance_attestation` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `pass` | outcome_model | kept | outcome_model |  |
| `rework` | outcome_model | kept | outcome_model |  |
| `exception` | outcome_model | converted | outcome_model | see notes below |
| `escalate` | outcome_model | converted | outcome_model | see notes below |
| `terminate` | outcome_model | converted | outcome_model | see notes below |
| `max_injection_success` | controls.tiering | moved | shared/guardrails.yaml | numeric safety/assurance limit → guardrail (FR-014) |
| `max_jailbreak_success` | controls.tiering | moved | shared/guardrails.yaml | numeric safety/assurance limit → guardrail (FR-014) |
| `pia` | controls.tiering | kept | controls.tiering |  |
| `red_team` | controls.tiering | kept | controls.tiering |  |
| `timeline.expected_duration` | timeline | kept | timeline |  |
| `timeline.reminder_after` | timeline | kept | timeline |  |
| `timeline.escalate_after` | timeline | kept | timeline |  |
| `timeline.max_rework_cycles` | timeline | kept | timeline |  |

Notes:

- `controls.tiering` `max_injection_success` / `max_jailbreak_success` moved to guardrails `injection_success_max` / `jailbreak_success_max` (renamed per Annex A); `red_team` and `pia` stay in tiering.
- Tiered sign-off placed under `sign_off.by_tier` (dictionary change).
- Columns renamed to snake_case: `privacy_assessment.class` → `data_class`, `rai_assurance.T4_actual` → `t4_actual`.
- Red-team and DLP measurements read from evidence sources `redteam` and `dlp`.

## T6 – Release Readiness

Source: TDS §10. File: `terminals/T6.yaml`.

| TDS element | TDS location | Result | New location | Reason |
| --- | --- | --- | --- | --- |
| `T5.pass` | trigger.on | kept | trigger.on |  |
| `T5.exception` | trigger.on | kept | trigger.on |  |
| `T9.reentry.T6` | trigger.on | removed | — | No T9 change class re-enters at this terminal (V-03: event never produced); re-entry stays possible by adding a change class. CoE to confirm. |
| `T7.rework.readiness_gap` | — | added | trigger.on | Added so the rework root-cause route that targets this terminal has a subscription (V-17). |
| `PRE-T6-01` | prerequisites | converted | prerequisites | `all in [pass, exception]` → `all_statuses_in(["T0", "T1", "T2", "T3", "T4", "T5"], ["pass", "exception"])`; evidence_ref `T0..T5.status` → `T5.status` |
| `PRE-T6-02` | prerequisites | converted | prerequisites | `signed` → `is_signed(T5.assurance_attestation)` |
| `PRE-T6-03` | prerequisites | converted | prerequisites | `requested` → `change.window_requested`; evidence_ref `change.window` → `change.window_requested` |
| `CTL-T6-01` | controls.automated | converted | controls.automated | `all prior terminal statuses in [pass, exception]` → `all_statuses_in(["T0", "T1", "T2", "T3", "T4", "T5"], ["pass", "exception"])` |
| `CTL-T6-02` | controls.automated | converted | controls.automated | `no waiver with expiry < release_date` → `no_waiver_expiring_before(release.release_date)` |
| `CTL-T6-03` | controls.automated | converted | controls.automated | `T4.bound_to == T5.bound_to == release.package_sha256` → `T4.bound_to == T5.bound_to && T5.bound_to == release.package_sha256` |
| `CTL-T6-04` | controls.automated | converted | controls.automated | `rollback_tested == true` → `all_rows_true(T6.rollback_strategy, "tested")` |
| `CTL-T6-05` | controls.automated | converted | controls.automated | `on_call rota and service_owner assigned` → `all_rows_have(T6.operational_ownership, ["team", "contact", "escalation"])` |
| `CTL-T6-06` | controls.automated | converted | controls.automated | `T8 alerts configured for every T1 KPI and T2 observability signal` → `alerts_cover(T6.monitoring_readiness, T1.kpis, T2.observability_design)` |
| `CTL-T6-07` | controls.automated | converted | controls.automated | `change_request.status == approved` → `change.request_status == "approved"` |
| `CHK-T6-01` | controls.checklist.items | moved | checklists/t6.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T6-02` | controls.checklist.items | moved | checklists/t6.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T6-03` | controls.checklist.items | moved | checklists/t6.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T6-04` | controls.checklist.items | moved | checklists/t6.yaml | Text moved to the checklist file; spec keeps the id |
| `gate_evidence_summary` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `deployment_package` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `runbook` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `rollback_strategy` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `rollout_plan` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `operational_ownership` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `support_readiness` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `monitoring_readiness` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `release_authorisation` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `pass` | outcome_model | kept | outcome_model |  |
| `rework` | outcome_model | kept | outcome_model |  |
| `exception` | outcome_model | converted | outcome_model | see notes below |
| `escalate` | outcome_model | converted | outcome_model | see notes below |
| `terminate` | outcome_model | converted | outcome_model | see notes below |
| `cab_required` | controls.tiering | kept | controls.tiering |  |
| `rollout` | controls.tiering | kept | controls.tiering |  |
| `timeline.expected_duration` | timeline | kept | timeline |  |
| `timeline.reminder_after` | timeline | kept | timeline |  |
| `timeline.escalate_after` | timeline | kept | timeline |  |
| `timeline.max_rework_cycles` | timeline | kept | timeline |  |

Notes:

- PRE-T6-01 `evidence_ref: T0..T5.status` is not a valid reference; it now references `T5.status` and the condition calls `all_statuses_in([...])`.
- PRE-T6-03 now references `change.window_requested`.
- `sign_off.external` free text became `{body: cab, when: tier.cab_required}`.
- `exception.when: go with conditions` is a human judgement, not computable; kept as `description`, route `T7`.
- Escalation route `business_owner_and_release_board` became destination `release_board` with `notify: [business_owner]`.

## T7 – Deployment & Transition

Source: TDS §11. File: `terminals/T7.yaml`.

| TDS element | TDS location | Result | New location | Reason |
| --- | --- | --- | --- | --- |
| `T6.pass` | trigger.on | kept | trigger.on |  |
| `T6.exception` | trigger.on | kept | trigger.on |  |
| `PRE-T7-01` | prerequisites | converted | prerequisites | `signed` → `is_signed(T6.release_authorisation)` |
| `PRE-T7-02` | prerequisites | converted | prerequisites | `now within window` → `within_window(change.window)` |
| `PRE-T7-03` | prerequisites | converted | prerequisites | `== T3.candidate_package.sha256` → `hash_matches(T6.deployment_package, T3.candidate_package)` |
| `CTL-T7-01` | controls.automated | converted | controls.automated | `deployed_hash == T6.deployment_package.sha256` → `hash_matches(env.prod, T6.deployment_package)` |
| `CTL-T7-02` | controls.automated | converted | controls.automated | `env_verification.all_green` → `all_rows_match(T7.env_config_verification, "result", "pass")` |
| `CTL-T7-03` | controls.automated | converted | controls.automated | `shadow quality within T4 baseline tolerance` → `within_baseline_tolerance(T7.stage_metrics, T4.eval_baseline, "shadow")` |
| `CTL-T7-04` | controls.automated | converted | controls.automated | `no alert breach during canary soak` → `no_breach_in_stage(T7.stage_metrics, "canary")` |
| `CTL-T7-05` | controls.automated | converted | controls.automated | `smoke_pass_rate == 100%` → `all_rows_match(T7.smoke_results, "result", "pass")` |
| `CTL-T7-06` | controls.automated | converted | controls.automated | `agent registered with owner, autonomy_level, version` → `all_rows_have(T7.registry_entry, ["owner", "autonomy_level", "version"])` |
| `CTL-T7-07` | controls.automated | converted | controls.automated | `hypercare: no open sev1/sev2 at exit` → `no_open_rows(T7.hypercare_log, "severity", ["sev1", "sev2"])` |
| `CHK-T7-01` | controls.checklist.items | moved | checklists/t7.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T7-02` | controls.checklist.items | moved | checklists/t7.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T7-03` | controls.checklist.items | moved | checklists/t7.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T7-04` | controls.checklist.items | moved | checklists/t7.yaml | Text moved to the checklist file; spec keeps the id |
| `deployment_log` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `env_config_verification` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `stage_metrics` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `smoke_results` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `hypercare_log` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `registry_entry` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `handover_acceptance` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `pass` | outcome_model | kept | outcome_model |  |
| `rework` | outcome_model | kept | outcome_model |  |
| `exception` | outcome_model | kept | outcome_model |  |
| `escalate` | outcome_model | converted | outcome_model | see notes below |
| `terminate` | outcome_model | converted | outcome_model | see notes below |
| `canary_pct` | controls.tiering | kept | controls.tiering |  |
| `hypercare` | controls.tiering | kept | controls.tiering |  |
| `soak` | controls.tiering | kept | controls.tiering |  |
| `timeline.expected_duration` | timeline | converted | timeline | `{'low': '1d+3d_hypercare', 'medium': '2d+7d_hypercare', 'high': '5d+14d_hypercare'}` → `{'low': '1d', 'medium': '2d', 'high': '5d'}` |
| `timeline.reminder_after` | timeline | kept | timeline |  |
| `timeline.escalate_after` | timeline | kept | timeline |  |
| `timeline.max_rework_cycles` | timeline | kept | timeline |  |

Notes:

- `expected_duration` `1d+3d_hypercare` etc. became `{low: 1d, medium: 2d, high: 5d}`; hypercare length stays in `controls.tiering.hypercare`.
- `terminate.then: T9.retire` removed: T9 already subscribes to `T7.terminate`, and `T9.retire` had no subscriber.
- Escalation route list `[sre_incident_bridge, service_owner]` became destination `incident_bridge` with `notify: [service_owner]`.
- `T7.rollback` is emitted because the spec declares `controls.auto_rollback_on`.

## T8 – Operate & Observe

Source: TDS §12. File: `terminals/T8.yaml`.

| TDS element | TDS location | Result | New location | Reason |
| --- | --- | --- | --- | --- |
| `T7.pass` | trigger.on | kept | trigger.on |  |
| `PRE-T8-01` | prerequisites | converted | prerequisites | `status == live` → `is_live(T7.registry_entry)` |
| `PRE-T8-02` | prerequisites | converted | prerequisites | `exists` → `evidence_exists(T6.monitoring_readiness)` |
| `PRE-T8-03` | prerequisites | converted | prerequisites | `frozen` → `is_frozen(T4.regression_pack)` |
| `CTL-T8-01` | controls.automated | converted | controls.automated | `all monitors reporting (no silent signals)` → `all_monitors_reporting()` |
| `CTL-T8-02` | controls.automated | converted | controls.automated | `regression replay pass_rate >= T4 baseline - tolerance` → `regression_within_baseline(T8.operating_health_report, T4.eval_baseline)` |
| `CTL-T8-03` | controls.automated | converted | controls.automated | `no open sev1/sev2 older than SLA` → `no_open_rows(T8.incident_problem_log, "severity", ["sev1", "sev2"])` |
| `CTL-T8-04` | controls.automated | converted | controls.automated | `no expired waivers` → `no_expired_waivers()` |
| `CHK-T8-01` | controls.checklist.items | moved | checklists/t8.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T8-02` | controls.checklist.items | moved | checklists/t8.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T8-03` | controls.checklist.items | moved | checklists/t8.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T8-04` | controls.checklist.items | moved | checklists/t8.yaml | Text moved to the checklist file; spec keeps the id |
| `MON-01` | monitors | converted | monitors | raises `event.safety_breach` → `T8.event.safety_breach`; threshold → `exceeds_threshold(telemetry.policy_violation_rate, T1.rai_thresholds, "policy_violation_rate")` |
| `MON-02` | monitors | converted | monitors | raises `event.safety_breach` → `T8.event.safety_breach`; threshold → `telemetry.pii_leak_count > 0` |
| `MON-03` | monitors | converted | monitors | raises `event.incident` → `T8.event.incident`; threshold → `below_nfr(telemetry.availability_pct, T1.non_functional_requirements, "availability")` |
| `MON-04` | monitors | converted | monitors | raises `event.drift` → `T8.event.drift`; threshold → `below_baseline(telemetry.online_eval_score, T4.eval_baseline)` |
| `MON-05` | monitors | converted | monitors | raises `event.cost_overrun` → `T8.event.cost_overrun`; threshold → `above_budget_for(telemetry.cost_per_task_usd, T2.token_budget, "7d")` |
| `MON-06` | monitors | converted | monitors | raises `event.kpi_shortfall` → `T8.event.kpi_shortfall`; threshold → `kpi_below_target_for(T1.kpis, telemetry.kpi_values, 3)` |
| `MON-07` | monitors | converted | monitors | raises `event.safety_breach` → `T8.event.safety_breach`; threshold → `telemetry.autonomy_breach_count > 0` |
| `MON-08` | monitors | converted | monitors | raises `event.upstream_change` → `T8.event.upstream_change`; threshold → `telemetry.upstream_deprecation_notice` |
| `MON-09` | monitors | converted | monitors | raises `event.waiver_expiring` → `T8.event.waiver_expiring`; threshold → `waiver_expiring_within("14d")` |
| `operating_health_report` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `incident_problem_log` | evidence.artifacts | renamed | evidence.artifacts | columns `id, severity, opened, closed, root_cause, linked_event` → `incident_id, severity, opened, closed, root_cause, linked_event` (Annex A); applicability mandatory |
| `drift_report` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `cost_report` | evidence.artifacts | renamed | evidence.artifacts | columns `period, tasks, tokens, cost, budget` → `period, task_count, token_count, cost_usd, budget_usd` (Annex A); applicability mandatory |
| `kpi_scorecard` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `feedback_themes` | evidence.artifacts | renamed | evidence.artifacts | columns `theme, volume, sentiment, action` → `theme, volume_count, sentiment, action` (Annex A); applicability mandatory |
| `raised_events` | evidence.artifacts | renamed | evidence.artifacts | columns `event_id, type, raised_at, routed_to, status` → `event_id, event_type, raised_at, routed_to, status` (Annex A); applicability mandatory |
| `pass` | outcome_model | converted | outcome_model | see notes below |
| `rework` | outcome_model | converted | outcome_model | see notes below |
| `exception` | outcome_model | converted | outcome_model | see notes below |
| `escalate` | outcome_model | converted | outcome_model | see notes below |
| `terminate` | outcome_model | converted | outcome_model | see notes below |
| `event.safety_breach` | outcome_model.event_routes | renamed | outcome_model.event_routes | key → `T8.event.safety_breach` |
| `event.incident` | outcome_model.event_routes | renamed | outcome_model.event_routes | key → `T8.event.incident` |
| `event.drift` | outcome_model.event_routes | renamed | outcome_model.event_routes | key → `T8.event.drift` |
| `event.cost_overrun` | outcome_model.event_routes | renamed | outcome_model.event_routes | key → `T8.event.cost_overrun` |
| `event.kpi_shortfall` | outcome_model.event_routes | renamed | outcome_model.event_routes | key → `T8.event.kpi_shortfall` |
| `event.upstream_change` | outcome_model.event_routes | renamed | outcome_model.event_routes | key → `T8.event.upstream_change` |
| `event.waiver_expiring` | outcome_model.event_routes | renamed | outcome_model.event_routes | key → `T8.event.waiver_expiring` |
| `timeline.expected_duration` | timeline | kept | timeline |  |
| `timeline.reminder_after` | timeline | converted | timeline | `2d_past_review_due` → `2d` |
| `timeline.escalate_after` | timeline | converted | timeline | `7d_past_review_due` → `7d` |
| `timeline.max_rework_cycles` | timeline | kept | timeline |  |

Notes:

- Monitor events `event.<name>` renamed `T8.event.<name>` (Annex A.3); free-text thresholds became expressions (MON-06 N = 3, MON-09 14d, MON-05 7d are proposed defaults).
- Event route `event.incident: {route: itsm, if_sev1: T7.rollback}` became `{route: itsm, then: T7.rollback, then_when: trigger.severity == "sev1"}`.
- `pass.route: T8.continue` became destination `continue`; `terminate.route: T9.retire` removed (T9 subscribes to `T8.terminate`).
- `sign_off.applies_to: periodic_review` removed: sign-off on a continuous terminal is always the periodic review.
- `timeline.reminder_after: 2d_past_review_due` / `escalate_after: 7d_past_review_due` became `2d` / `7d`, measured from `review_due` (dictionary change).
- Columns renamed (Annex A): `incident_problem_log.id` → `incident_id`, `cost_report` → `task_count`/`token_count`/`cost_usd`/`budget_usd`, `feedback_themes.volume` → `volume_count`, `raised_events.type` → `event_type`.

## T9 – Evolve / Retire

Source: TDS §13. File: `terminals/T9.yaml`.

| TDS element | TDS location | Result | New location | Reason |
| --- | --- | --- | --- | --- |
| `T8.event.drift` | trigger.on | kept | trigger.on |  |
| `T8.event.cost_overrun` | trigger.on | kept | trigger.on |  |
| `T8.event.kpi_shortfall` | trigger.on | kept | trigger.on |  |
| `T8.event.upstream_change` | trigger.on | kept | trigger.on |  |
| `change.requested` | trigger.on | kept | trigger.on |  |
| `lifecycle.review_due` | trigger.on | kept | trigger.on |  |
| `T8.terminate` | trigger.on | kept | trigger.on |  |
| `T7.terminate` | trigger.on | kept | trigger.on |  |
| `PRE-T9-01` | prerequisites | converted | prerequisites | `exists` → `evidence_exists(trigger.evidence)` |
| `PRE-T9-02` | prerequisites | converted | prerequisites | `exists` → `evidence_exists(T3.build_manifest)`; evidence_ref `T3.build_manifest.current` → `T3.build_manifest` |
| `PRE-T9-03` | prerequisites | converted | prerequisites | `exists` → `evidence_exists(T4.regression_pack)`; evidence_ref `T4.regression_pack.current` → `T4.regression_pack` |
| `CTL-T9-01` | controls.automated | converted | controls.automated | `change_class assigned and reentry >= class minimum` → `reentry_consistent(T9.change_impact_assessment)` |
| `CTL-T9-02` | controls.automated | converted | controls.automated | `autonomy or data class change => class >= major` → `class_at_least_if(T9.change_impact_assessment, ["autonomy", "data_class"], "major")` |
| `CTL-T9-03` | controls.automated | converted | controls.automated | `model or tool change => class >= moderate` → `class_at_least_if(T9.change_impact_assessment, ["model", "tool"], "moderate")` |
| `CTL-T9-04` | controls.automated | converted | controls.automated | `retire: all credentials revoked` → `run.mode != "retire" \|\| retirement.credentials_revoked` |
| `CTL-T9-05` | controls.automated | converted | controls.automated | `retire: data disposition evidenced per T2 retention` → `run.mode != "retire" \|\| retirement.data_disposed` |
| `CTL-T9-06` | controls.automated | converted | controls.automated | `retire: no dependent agent left unowned` → `run.mode != "retire" \|\| retirement.unowned_dependants == 0` |
| `CHK-T9-01` | controls.checklist.items | moved | checklists/t9.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T9-02` | controls.checklist.items | moved | checklists/t9.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T9-03` | controls.checklist.items | moved | checklists/t9.yaml | Text moved to the checklist file; spec keeps the id |
| `CHK-T9-04` | controls.checklist.items | moved | checklists/t9.yaml | Text moved to the checklist file; spec keeps the id |
| `change_impact_assessment` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `revalidation_plan` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `version_lifecycle_record` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `lessons_learned` | evidence.artifacts | kept | evidence.artifacts | applicability mandatory |
| `retirement_record` | evidence.artifacts | kept | evidence.artifacts | applicability conditional |
| `closure_report` | evidence.artifacts | kept | evidence.artifacts | applicability conditional |
| `pass` | outcome_model | converted | outcome_model | see notes below |
| `rework` | outcome_model | kept | outcome_model |  |
| `exception` | outcome_model | converted | outcome_model | see notes below |
| `escalate` | outcome_model | converted | outcome_model | see notes below |
| `terminate` | outcome_model | converted | outcome_model | see notes below |
| `timeline.expected_duration` | timeline | converted | timeline | `{'assessment': '2d', 'retirement': {'low': '5d', 'medium': '10d', 'high': '20d'}}` → `{'low': '2d', 'medium': '2d', 'high': '2d'}` |
| `timeline.reminder_after` | timeline | kept | timeline |  |
| `timeline.escalate_after` | timeline | kept | timeline |  |
| `timeline.max_rework_cycles` | timeline | kept | timeline |  |

Notes:

- `pass: {route: ${change_impact_assessment.reentry_terminal}, or: lifecycle.closed}` became `route: "${T9.change_impact_assessment.reentry_terminal}"` with `alternatives: [lifecycle_closed]`.
- Change class `strategic` `or: retire` became `alternative: lifecycle_closed`.
- Sign-off per mode placed under `sign_off.by_mode`; `retirement.requires: business_owner_approval` became role `business_owner`.
- `expected_duration: {assessment: 2d, retirement: {...}}` split into `expected_duration` (2d every tier) and `retirement_duration`.
- PRE-T9-02/03 `.current` suffix dropped: evidence reads always take the latest ledger record.
- Retire-only controls CTL-T9-04..06 are conditioned on `run.mode != "retire" || ...`; retire-only artifacts are conditional on `run.mode == "retire"`.
- `terminate.meaning` kept as `description`.

## Changes after conversion: feature 010 (MCP servers)

- `shared/mcp_servers.yaml` 2.0.0: every server names its `host` (knowledge, tools or bridge);
  new server `pilot_env` (scopes `dev`, `test`, `read`); `cd` gains `read`.
- T3 2.0.0: tool scopes add `mcp:pilot_env:dev`, `mcp:pilot_env:read`, `mcp:git:read`,
  `mcp:artifact_store:read` (T3 provisions the dev environment and reads its own branch and builds).
- T4 2.0.0: add `mcp:pilot_env:test`, `mcp:pilot_env:read`, `mcp:artifact_store:read`.
- T5 2.0.0: add `mcp:pilot_env:test`, `mcp:pilot_env:read`.
- `confluence` write (T6 runbooks, T9 lessons) is not served yet: the knowledge server is read-only.
  T6 and T9 keep those texts as artifacts until a writable wiki server exists.
